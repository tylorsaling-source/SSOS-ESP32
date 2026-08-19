from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass(frozen=True)
class ModelConfig:
    vocab_size: int = 940
    dim: int = 96
    hidden_dim: int = 192
    n_layers: int = 4
    n_heads: int = 4
    max_seq_len: int = 256
    split_layer: int = 2
    rms_eps: float = 1e-6

    @classmethod
    def load(cls, path: Path) -> "ModelConfig":
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: raw[k] for k in cls.__dataclass_fields__ if k in raw})


class RMSNorm(nn.Module):
    def __init__(self, dim: int, eps: float):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        scale = torch.rsqrt(x.float().pow(2).mean(-1, keepdim=True) + self.eps)
        return (x * scale.to(x.dtype)) * self.weight


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


class Attention(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.n_heads = cfg.n_heads
        self.head_dim = cfg.dim // cfg.n_heads
        self.q = nn.Linear(cfg.dim, cfg.dim, bias=False)
        self.k = nn.Linear(cfg.dim, cfg.dim, bias=False)
        self.v = nn.Linear(cfg.dim, cfg.dim, bias=False)
        self.o = nn.Linear(cfg.dim, cfg.dim, bias=False)

    def forward(self, x: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
        b, t, d = x.shape
        q = self.q(x).view(b, t, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k(x).view(b, t, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v(x).view(b, t, self.n_heads, self.head_dim).transpose(1, 2)
        inv = 1.0 / (10000.0 ** (torch.arange(0, self.head_dim, 2, device=x.device).float() / self.head_dim))
        freq = torch.outer(positions.float(), inv)
        emb = torch.cat((freq, freq), dim=-1)[None, None, :, :]
        q = q * emb.cos().to(q.dtype) + _rotate_half(q) * emb.sin().to(q.dtype)
        k = k * emb.cos().to(k.dtype) + _rotate_half(k) * emb.sin().to(k.dtype)
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self.o(y.transpose(1, 2).contiguous().view(b, t, d))


class FeedForward(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.w1 = nn.Linear(cfg.dim, cfg.hidden_dim, bias=False)
        self.w2 = nn.Linear(cfg.hidden_dim, cfg.dim, bias=False)
        self.w3 = nn.Linear(cfg.dim, cfg.hidden_dim, bias=False)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.w2(F.silu(self.w1(x)) * self.w3(x))


class Block(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.attn_norm = RMSNorm(cfg.dim, cfg.rms_eps)
        self.ffn_norm = RMSNorm(cfg.dim, cfg.rms_eps)
        self.attn = Attention(cfg)
        self.ffn = FeedForward(cfg)

    def forward(self, x: torch.Tensor, positions: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.attn_norm(x), positions)
        return x + self.ffn(self.ffn_norm(x))


class MasterStage(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.embedding = nn.Embedding(cfg.vocab_size, cfg.dim)
        self.layers = nn.ModuleList(Block(cfg) for _ in range(cfg.split_layer))

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(tokens.shape[1], device=tokens.device)
        x = self.embedding(tokens)
        for layer in self.layers:
            x = layer(x, positions)
        return x


class WorkerStage(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.layers = nn.ModuleList(Block(cfg) for _ in range(cfg.split_layer, cfg.n_layers))
        self.norm = RMSNorm(cfg.dim, cfg.rms_eps)
        self.output = nn.Linear(cfg.dim, cfg.vocab_size, bias=False)

    def forward(self, activation: torch.Tensor) -> torch.Tensor:
        positions = torch.arange(activation.shape[1], device=activation.device)
        x = activation
        for layer in self.layers:
            x = layer(x, positions)
        return self.output(self.norm(x))


class SplitModel(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.master = MasterStage(cfg)
        self.worker = WorkerStage(cfg)
        self.apply(self._init)

    @staticmethod
    def _init(module: nn.Module) -> None:
        if isinstance(module, (nn.Linear, nn.Embedding)):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(self, tokens: torch.Tensor) -> torch.Tensor:
        return self.worker(self.master(tokens))

    def parameter_counts(self) -> dict[str, int]:
        return {
            "master": sum(p.numel() for p in self.master.parameters()),
            "worker": sum(p.numel() for p in self.worker.parameters()),
            "total": sum(p.numel() for p in self.parameters()),
        }


def split_loss_backward(
    model: SplitModel,
    tokens: torch.Tensor,
    targets: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    activation = model.master(tokens)
    wire_activation = activation.detach().requires_grad_(True)
    logits = model.worker(wire_activation)
    loss = F.cross_entropy(logits.reshape(-1, model.cfg.vocab_size), targets.reshape(-1))
    loss.backward()
    if wire_activation.grad is None:
        raise RuntimeError("worker did not produce a boundary gradient")
    boundary_gradient = wire_activation.grad.detach().clone()
    activation.backward(boundary_gradient)
    return loss.detach(), boundary_gradient
