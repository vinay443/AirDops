/* AirDops per-frame audio maths, compiled into the same library as RNNoise.
 *
 * The realtime callback calls these two functions once per 10 ms frame, so the
 * sample loops (downmix, scaling, gate ramp, gain, clipping, level) run in C
 * instead of Python and nothing is allocated while audio is running.
 *
 * Copyright (c) AirDops contributors. MIT License.
 */
#include "rnnoise.h"

#if defined(_WIN32)
#  define AIRDOPS_EXPORT __declspec(dllexport)
#elif defined(__GNUC__)
#  define AIRDOPS_EXPORT __attribute__((visibility("default")))
#else
#  define AIRDOPS_EXPORT
#endif

#define AIRDOPS_FRAME 480
#define AIRDOPS_SCALE 32767.0f

/* Downmix `n` interleaved float frames (samples in [-1, 1]) to mono in `buf`,
 * scaled to the 16-bit range RNNoise expects, zero-pad to 480 samples and
 * denoise in place. With st == NULL the audio is passed through untouched.
 * Returns RNNoise's voice probability (1.0 for pass-through). */
AIRDOPS_EXPORT float airdops_denoise(DenoiseState *st, const float *in, int channels, int n, float *buf)
{
    int i, c;
    float inv;
    if (n > AIRDOPS_FRAME) n = AIRDOPS_FRAME;
    if (n < 0) n = 0;
    if (channels < 1) channels = 1;
    inv = AIRDOPS_SCALE / (float)channels;
    for (i = 0; i < n; i++) {
        float acc = 0.0f;
        for (c = 0; c < channels; c++) acc += in[i * channels + c];
        buf[i] = acc * inv;
    }
    for (; i < AIRDOPS_FRAME; i++) buf[i] = 0.0f;
    if (st == NULL) return 1.0f;
    return rnnoise_process_frame(st, buf, buf);
}

/* Write `n` samples of `buf` (16-bit range) to every channel of the
 * interleaved float output, applying a linear gate ramp g0 -> g1 across the
 * frame (same as numpy.linspace), a post gain, and clipping to [-1, 1].
 * Returns the sum of squares of the output, for the level meter. */
AIRDOPS_EXPORT double airdops_finish(const float *buf, int n, float g0, float g1, float post, float *out, int channels)
{
    int i, c;
    double sumsq = 0.0;
    float step;
    if (n > AIRDOPS_FRAME) n = AIRDOPS_FRAME;
    if (channels < 1) channels = 1;
    step = n > 1 ? (g1 - g0) / (float)(n - 1) : 0.0f;
    for (i = 0; i < n; i++) {
        float v = buf[i] * (1.0f / AIRDOPS_SCALE) * (g0 + step * (float)i) * post;
        if (v > 1.0f) v = 1.0f;
        else if (v < -1.0f) v = -1.0f;
        sumsq += (double)v * (double)v;
        for (c = 0; c < channels; c++) out[i * channels + c] = v;
    }
    return sumsq;
}
