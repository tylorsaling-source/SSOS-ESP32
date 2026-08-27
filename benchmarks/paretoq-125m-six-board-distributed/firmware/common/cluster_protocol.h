#pragma once

#include <stddef.h>
#include <stdint.h>

namespace paretoq {

constexpr uint32_t kClusterMagic = 0x50513125u;
constexpr uint32_t kClusterSpiHz = 40000000u;
constexpr uint8_t kBroadcastStage = 0xFFu;

enum ClusterKind : uint8_t {
  kClusterRunLayers = 1,
  kClusterStartLogits = 2,
  kClusterCollectLogits = 3,
  kClusterFetchEmbedding = 4,
  kClusterReset = 5,
  kClusterPipelineEmbedding = 6,
  kClusterPipelineLayers = 7,
  kClusterPipelineLogits = 8,
  kClusterReply = 0x80,
};

enum ClusterMode : uint8_t {
  kClusterRegular = 0,
  kClusterFast = 1,
};

#pragma pack(push, 1)
struct ClusterPacket {
  uint32_t magic;
  uint32_t sequence;
  uint32_t checksum;
  uint32_t compute_us;
  uint16_t token;
  uint16_t position;
  uint16_t best_token;
  uint16_t payload_words;
  float best_logit;
  uint8_t target_stage;
  uint8_t source_stage;
  uint8_t kind;
  uint8_t mode;
  uint8_t stream_id;
  uint8_t reserved[3];
  uint16_t payload[576];
};
#pragma pack(pop)

static_assert(sizeof(ClusterPacket) == 1188, "cluster packet size changed");

inline uint32_t cluster_checksum(const ClusterPacket& packet) {
  const uint8_t* bytes = reinterpret_cast<const uint8_t*>(&packet);
  uint32_t hash = 2166136261u;
  for (size_t index = offsetof(ClusterPacket, compute_us); index < sizeof(packet); ++index) {
    hash ^= bytes[index];
    hash *= 16777619u;
  }
  hash ^= packet.magic;
  hash *= 16777619u;
  hash ^= packet.sequence;
  hash *= 16777619u;
  return hash;
}

inline bool cluster_packet_valid(const ClusterPacket& packet) {
  return packet.magic == kClusterMagic && packet.payload_words <= 576 &&
      packet.checksum == cluster_checksum(packet);
}

inline void cluster_packet_seal(ClusterPacket& packet) {
  packet.checksum = cluster_checksum(packet);
}

}  // namespace paretoq
