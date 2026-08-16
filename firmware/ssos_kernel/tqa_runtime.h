#pragma once
#include <stdint.h>

void tensorInit();
void tensorOnRecv(uint8_t used, uint8_t cap);
void tensorOnGet(bool hit);
void tensorOnFault();
void tensorTick();
void tensorPrint();
void tensorResetSeed();
bool tensorSetW(int i, float v);
uint16_t tensorBurst();
uint16_t tensorRestMs();
uint16_t tensorFlushN();
uint16_t tensorScale();
int tensorDominant();
float tensorScore();
void tensorLoadW(const float w[9]);
void tensorSaveW(float w[9]);
uint32_t tensorRestUntil();
uint32_t tensorSinceFlush();
void tensorClearFlush();

// Fused 9→8: parse x once, 72 contiguous weights, eight outputs.
void tensorFuse98(const float *x9, float *y8);
void tensorEightDots(const float *x9, float *y8);
void tensorOnRecvNaive8(uint8_t used, uint8_t cap);
const float *tensorW72();
void tensorCopyY8(float out[8]);
void tensorCopyX(float out[9]);
