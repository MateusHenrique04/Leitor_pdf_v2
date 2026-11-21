package com.lector.app.tts;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;

/**
 * Porte do módulo drm.py da biblioteca edge-tts 7.2.8 (geração do token Sec-MS-GEC, formato "v2").
 *
 * Escrito em Java (e não Kotlin) de propósito: foi conferido contra o drm.py original com a mesma
 * entrada, e a aritmética de 32 bits fica idêntica à do Python usando long + máscara.
 *
 * Se a Microsoft mudar o algoritmo, o endpoint passa a recusar a conexão (HTTP 403 mesmo com o relógio
 * certo). Aí é preciso portar o drm.py de uma versão nova do edge-tts.
 */
public final class EdgeDrm {
    private EdgeDrm() {}

    private static final long MASK = 0xFFFFFFFFL;
    private static final long WIN_EPOCH = 11644473600L;

    private static final long[] SHA256_INITIAL = {
        0x6A09E667L, 0xBB67AE85L, 0x3C6EF372L, 0xA54FF53AL,
        0x510E527FL, 0x9B05688CL, 0x1F83D9ABL, 0x5BE0CD19L,
    };
    private static final long[] SHA256_STATE = {
        0xFD9FBEA2L, 0x91243CE7L, 0xBE499094L, 0xCD2E1E0AL,
        0x6C006F49L, 0x04BD35ABL, 0xFEB0A7E4L, 0x03EFFBD2L,
    };
    private static final long[] SHA256_SCHEDULE = {
        0xEB24BF9EL, 0x1558691FL, 0xA0C09EE2L, 0x0CFA32BAL, 0xA622EE8CL, 0xD1DD9491L, 0xC0DD25A0L,
        0xF9E70AB6L, 0xF0C31573L, 0x7058CE4EL, 0x7188E606L, 0x00E5AB33L, 0xD258B060L, 0x72766564L,
    };
    private static final long[] ROUND_CONSTANTS = {
        0x428A2F98L, 0x71374491L, 0xB5C0FBCFL, 0xE9B5DBA5L, 0x3956C25BL, 0x59F111F1L, 0x923F82A4L, 0xAB1C5ED5L,
        0xD807AA98L, 0x12835B01L, 0x243185BEL, 0x550C7DC3L, 0x72BE5D74L, 0x80DEB1FEL, 0x9BDC06A7L, 0xC19BF174L,
        0xE49B69C1L, 0xEFBE4786L, 0x0FC19DC6L, 0x240CA1CCL, 0x2DE92C6FL, 0x4A7484AAL, 0x5CB0A9DCL, 0x76F988DAL,
        0x983E5152L, 0xA831C66DL, 0xB00327C8L, 0xBF597FC7L, 0xC6E00BF3L, 0xD5A79147L, 0x06CA6351L, 0x14292967L,
        0x27B70A85L, 0x2E1B2138L, 0x4D2C6DFCL, 0x53380D13L, 0x650A7354L, 0x766A0ABBL, 0x81C2C92EL, 0x92722C85L,
        0xA2BFE8A1L, 0xA81A664BL, 0xC24B8B70L, 0xC76C51A3L, 0xD192E819L, 0xD6990624L, 0xF40E3585L, 0x106AA070L,
        0x19A4C116L, 0x1E376C08L, 0x2748774CL, 0x34B0BCB5L, 0x391C0CB3L, 0x4ED8AA4AL, 0x5B9CCA4FL, 0x682E6FF3L,
        0x748F82EEL, 0x78A5636FL, 0x84C87814L, 0x8CC70208L, 0x90BEFFFAL, 0xA4506CEBL, 0xBEF9A3F7L, 0xC67178F2L,
    };
    private static final long SHA256_ADJUSTMENT = 0xC9DC06A7L;
    private static final long SIGMA0_ADJUSTMENT = 0x059C0B80L;
    private static final long SIGMA1_ADJUSTMENT = 0x000B92C0L;
    private static final long[] BLOCK_CONSTANTS = blockConstants();

    private static long[] blockConstants() {
        long[] c = ROUND_CONSTANTS.clone();
        c[14] = SHA256_ADJUSTMENT;
        return c;
    }

    /** {coeficiente, deslocamento}. */
    private static final long[][] CS64_COEFFICIENTS = {
        {0xE82E91B1L, 0xB32700D0L}, {0x44DE24C6L, 0x88DFF51DL}, {0x3BEB65BCL, 0x29514038L},
        {0xC89C5933L, 0xB328CBDFL}, {0x8D1EC211L, 0xD405B4D5L}, {0x314EF5D5L, 0x26E55F3CL},
        {0xE92491B1L, 0x607801C6L}, {0xF0A5B9D5L, 0x82B2C1FBL}, {0x06064CF3L, 0xFA51A3DAL},
        {0xDA79FA60L, 0x207CC464L}, {0xBED20560L, 0x3C3C74F3L}, {0x89F9C9F8L, 0xD2D14B61L},
        {0x35FA38C6L, 0xBB04A2C1L}, {0xCB49E3C6L, 0xC5626167L},
    };
    private static final long CS64_FACTOR = 0x82893933L;
    private static final long CS64_ADJUSTMENT0 = 0xF2F90B1AL;
    private static final long CS64_ADJUSTMENT1 = 0x0B1A0000L;

    private static long rol16(long value) {
        value &= MASK;
        return ((value << 16) | (value >>> 16)) & MASK;
    }

    private static long sigma0(long v) {
        return ((v >>> 7) ^ (v << 25) ^ (v >>> 18) ^ (v << 14) ^ (v >>> 3)) & MASK;
    }

    private static long sigma1(long v) {
        return ((v >>> 17) ^ (v << 15) ^ (v >>> 19) ^ (v << 13) ^ (v >>> 10)) & MASK;
    }

    /** Roda as rodadas do SHA-256 de [firstRound] até 63 (versão simples do original, que desenrola o laço). */
    private static long[] sha256Rounds(long[] state, long[] words, int firstRound) {
        long a = state[0], b = state[1], c = state[2], d = state[3];
        long e = state[4], f = state[5], g = state[6], h = state[7];
        long[] constants = (firstRound == 14) ? BLOCK_CONSTANTS : ROUND_CONSTANTS;
        for (int i = firstRound; i < 64; i++) {
            long rotE = e * 0x100000001L;
            long rotA = a * 0x100000001L;
            long t1 = h + ((rotE >>> 6) ^ (rotE >>> 11) ^ (rotE >>> 25)) + (g ^ (e & (f ^ g))) + constants[i] + words[i];
            long t2 = ((rotA >>> 2) ^ (rotA >>> 13) ^ (rotA >>> 22)) + ((a & b) | (c & (a | b)));
            long na = (t1 + t2) & MASK;
            long ne = (d + t1) & MASK;
            h = g; g = f; f = e; e = ne;
            d = c; c = b; b = a; a = na;
        }
        return new long[] {a, b, c, d, e, f, g, h};
    }

    /** Completa words[firstWord..63] (words[0..firstWord-1] já preenchidos). */
    private static void expandSchedule(long[] words, int firstWord) {
        for (int i = firstWord; i < 64; i++) {
            long x = words[i - 2];
            long y = words[i - 15];
            long s1 = (x >>> 17) ^ (x << 15) ^ (x >>> 19) ^ (x << 13) ^ (x >>> 10);
            long s0 = (y >>> 7) ^ (y << 25) ^ (y >>> 18) ^ (y << 14) ^ (y >>> 3);
            words[i] = (s1 + words[i - 7] + s0 + words[i - 16]) & MASK;
        }
    }

    private static long fromBytesBE(byte[] data, int from, int to) {
        long v = 0;
        for (int i = from; i < to; i++) v = (v << 8) | (data[i] & 0xFFL);
        return v;
    }

    private static long[] sha256Init(byte[] salt7) {
        long[] words = new long[64];
        words[14] = fromBytesBE(salt7, 0, 3);
        words[15] = fromBytesBE(salt7, 3, 7);
        for (int index = 16; index < 30; index++) {
            long value = SHA256_SCHEDULE[index - 16];
            if (index - 2 >= 14) {
                value += (index == 16) ? (sigma1(words[index - 2]) ^ SIGMA1_ADJUSTMENT) : sigma1(words[index - 2]);
            }
            if (index - 7 >= 14) {
                value += words[index - 7];
            }
            if (index - 15 >= 14) {
                value += (index == 29) ? (sigma0(words[index - 15]) ^ SIGMA0_ADJUSTMENT) : sigma0(words[index - 15]);
            }
            words[index] = value & MASK;
        }
        words[30] = (sigma1(words[28]) + words[23] + sigma0(words[15]) + words[14]
                + SHA256_ADJUSTMENT - ROUND_CONSTANTS[14]) & MASK;
        expandSchedule(words, 31);
        long[] working = sha256Rounds(SHA256_STATE, words, 14);
        long[] out = new long[8];
        for (int i = 0; i < 8; i++) out[i] = (SHA256_INITIAL[i] + working[i]) & MASK;
        return out;
    }

    private static byte[] sha256Digest(byte[] data) {
        if (data.length < 7) throw new IllegalArgumentException("Token salt must contain at least seven bytes");
        long length = 57L + data.length;
        int padZeros = (int) Math.floorMod(55L - length, 64L);
        int paddedLen = (data.length - 7) + 1 + padZeros + 8;
        byte[] padded = new byte[paddedLen];
        System.arraycopy(data, 7, padded, 0, data.length - 7);
        padded[data.length - 7] = (byte) 0x80;
        long bits = length * 8;
        for (int i = 0; i < 8; i++) padded[paddedLen - 1 - i] = (byte) (bits >>> (8 * i));

        byte[] salt = new byte[7];
        System.arraycopy(data, 0, salt, 0, 7);
        long[] state = sha256Init(salt);
        long[] words = new long[64];
        for (int offset = 0; offset < paddedLen; offset += 64) {
            for (int i = 0; i < 16; i++) {
                words[i] = fromBytesBE(padded, offset + 4 * i, offset + 4 * i + 4);
            }
            expandSchedule(words, 16);
            long[] working = sha256Rounds(state, words, 0);
            for (int i = 0; i < 8; i++) state[i] = (state[i] + working[i]) & MASK;
        }
        byte[] out = new byte[32];
        for (int i = 0; i < 8; i++) {
            out[4 * i] = (byte) (state[i] >>> 24);
            out[4 * i + 1] = (byte) (state[i] >>> 16);
            out[4 * i + 2] = (byte) (state[i] >>> 8);
            out[4 * i + 3] = (byte) state[i];
        }
        return out;
    }

    private static long leWord(byte[] b, int off) {
        return (b[off] & 0xFFL) | ((b[off + 1] & 0xFFL) << 8) | ((b[off + 2] & 0xFFL) << 16) | ((b[off + 3] & 0xFFL) << 24);
    }

    /** Palavras de 32 bits little-endian de (0x00 + data), com zeros no fim até ter quantidade par. */
    private static long[] wordsLe4Even(byte[] data) {
        int n = data.length + 1;
        int padded = n + ((4 - n % 4) % 4);
        byte[] buf = new byte[padded];
        System.arraycopy(data, 0, buf, 1, data.length);
        int count = padded / 4;
        if (count % 2 == 1) count++;
        long[] words = new long[count];
        for (int i = 0; i < padded / 4; i++) words[i] = leWord(buf, 4 * i);
        return words;
    }

    private static long[] cs64Digest(byte[] data, byte[] digest) {
        long keyA = leWord(digest, 0) | 1;
        long keyB = leWord(digest, 4) | 1;
        long[] factors = {(keyA * CS64_FACTOR) & MASK, (keyB * CS64_FACTOR) & MASK};
        long[] dataWords = wordsLe4Even(data);
        int base = CS64_COEFFICIENTS.length;
        long[] terms = new long[base + dataWords.length];
        long[] offsets = new long[base + dataWords.length];
        for (int i = 0; i < base; i++) {
            terms[i] = (CS64_COEFFICIENTS[i][0] * factors[i % 2]) & MASK;
            offsets[i] = CS64_COEFFICIENTS[i][1];
        }
        for (int i = 0; i < dataWords.length; i++) {
            long word = dataWords[i];
            long term = word * ((i % 2 == 0) ? keyA : keyB);
            long offset = rol16(word) * ((i % 2 == 0) ? 0xEF0569FBL : 0xC31713DBL);
            if (i == 0) {
                term += CS64_ADJUSTMENT0 * factors[0];
                offset += CS64_ADJUSTMENT1;
            }
            terms[base + i] = term & MASK;
            offsets[base + i] = offset & MASK;
        }
        long swapAcc = 0, swapLast = 0, state = 0, acc = 0;
        for (int i = 0; i < terms.length; i += 2) {
            long x = terms[i];
            long y = terms[i + 1];
            long t = rol16((offsets[i] + x) & MASK);
            long q = (t * 0x76F50F34L) & MASK;
            swapAcc += (rol16(q) * 0xC3EFEA97L + q) & MASK;
            t = rol16((offsets[i + 1] + y) & MASK);
            q = (t * 0x1881CE3CL) & MASK;
            swapLast = (rol16(q) * 0x35BD1EC9L + q) & MASK;
            swapAcc = (swapAcc + swapLast) & MASK;

            state = (state * keyA + x) & MASK;
            state = (rol16(state) * 0xCF98B111L) & MASK;
            state = (rol16(state) * 0x87085B9FL) & MASK;
            state = (rol16(state) * 0x12CEB96DL) & MASK;
            state = (rol16(state) * 0x257E1D83L) & MASK;
            acc += state;
            t = (state * keyB + y) & MASK;
            t = (rol16(t) * 0xA27416F5L) & MASK;
            t = (rol16(t) * 0xD38396FFL) & MASK;
            state = (rol16((rol16(t) * 0x7C932B89L) & MASK) * 0xBFA49F69L) & MASK;
            acc = (acc + state) & MASK;
        }
        return new long[] {swapLast ^ state, swapAcc ^ acc};
    }

    private static final char[] HEX = "0123456789ABCDEF".toCharArray();

    private static void appendHex(StringBuilder sb, byte b) {
        sb.append(HEX[(b >> 4) & 0xF]).append(HEX[b & 0xF]);
    }

    /** Token v2 para [token] (TRUSTED_CLIENT_TOKEN) e o instante [unixSeconds] (já com correção de relógio). */
    public static String generateSecMsGec(double unixSeconds, String trustedClientToken) {
        double ticks = unixSeconds;
        ticks += WIN_EPOCH;
        ticks -= ticks % 300;
        ticks *= 1e9 / 100; // S_TO_NS / 100, como no Python
        // f"{ticks:.0f}": o valor exato do double, sem casas decimais.
        String ticksStr = new BigDecimal(ticks).setScale(0, RoundingMode.HALF_EVEN).toPlainString();
        byte[] data = (ticksStr + trustedClientToken).getBytes(StandardCharsets.US_ASCII);

        byte[] digest = sha256Digest(data);
        long[] cs = cs64Digest(data, digest);
        StringBuilder sb = new StringBuilder(81);
        for (int w = 0; w < 2; w++) {
            for (int i = 0; i < 4; i++) appendHex(sb, (byte) (cs[w] >>> (8 * i))); // little-endian
        }
        sb.append('-');
        for (byte b : digest) appendHex(sb, b);
        return sb.toString();
    }
}
