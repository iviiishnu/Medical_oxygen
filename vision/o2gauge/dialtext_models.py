"""Dial-text networks (PyTorch, training / export only - inference runs the ONNX files).

TextDet  : dial crop or bezel strips (RGB, 0..1) -> text-region logits at half resolution
           (target = every word / number box shrunk by 20 % of its height, like DBNet)
TextRec  : one text crop (gray, -1..1, 32 x 192) -> per-column character logits (CTC)
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from .dialtext_geom import CHARS


def cbr(i, o, s=1, d=1):
    return nn.Sequential(nn.Conv2d(i, o, 3, s, d, dilation=d, bias=False), nn.BatchNorm2d(o), nn.ReLU(inplace=True))


class TextDet(nn.Module):
    def __init__(self):
        super().__init__()
        self.e0 = nn.Sequential(cbr(3, 16, 2), cbr(16, 16))          # 1/2
        self.e1 = nn.Sequential(cbr(16, 32, 2), cbr(32, 32))         # 1/4
        self.e2 = nn.Sequential(cbr(32, 64, 2), cbr(64, 64))         # 1/8
        self.e3 = nn.Sequential(cbr(64, 96, 2), cbr(96, 96, d=2))    # 1/16
        self.e4 = nn.Sequential(cbr(96, 128, 2), cbr(128, 128, d=2), cbr(128, 128))  # 1/32
        self.d3 = cbr(128 + 96, 96)
        self.d2 = cbr(96 + 64, 64)
        self.d1 = cbr(64 + 32, 32)
        self.d0 = nn.Sequential(cbr(32 + 16, 32), cbr(32, 32))
        self.head = nn.Conv2d(32, 1, 1)

    @staticmethod
    def _up(x):
        return F.interpolate(x, scale_factor=2.0, mode="nearest")

    def forward(self, x):
        x = (x - 0.5) / 0.25
        e0 = self.e0(x)
        e1 = self.e1(e0)
        e2 = self.e2(e1)
        e3 = self.e3(e2)
        e4 = self.e4(e3)
        y = self.d3(torch.cat([self._up(e4), e3], 1))
        y = self.d2(torch.cat([self._up(y), e2], 1))
        y = self.d1(torch.cat([self._up(y), e1], 1))
        y = self.d0(torch.cat([self._up(y), e0], 1))
        return self.head(y)


class TextRec(nn.Module):
    def __init__(self, n_class: int = len(CHARS) + 1):
        super().__init__()
        self.cnn = nn.Sequential(
            cbr(1, 32), nn.MaxPool2d(2),                 # 16 x 96
            cbr(32, 64), nn.MaxPool2d(2),                # 8 x 48
            cbr(64, 128), cbr(128, 128), nn.MaxPool2d((2, 1)),   # 4 x 48
            cbr(128, 192), cbr(192, 192), nn.MaxPool2d((2, 1)),  # 2 x 48
            nn.Conv2d(192, 256, (2, 1), bias=False), nn.BatchNorm2d(256), nn.ReLU(inplace=True))  # 1 x 48
        # sequence context with dilated 1-D convolutions (an LSTM's backward pass fails in MIOpen on
        # gfx1032, and convolutions are faster on the CPU at inference anyway)
        self.seq = nn.ModuleList([nn.Sequential(nn.Conv1d(256, 256, 3, padding=d, dilation=d, bias=False),
                                                nn.BatchNorm1d(256), nn.ReLU(inplace=True)) for d in (1, 2, 4, 1)])
        self.fc = nn.Conv1d(256, n_class, 1)

    def forward(self, x):                                 # (B, 1, 32, W) -> (B, W/4, C)
        f = self.cnn(x).squeeze(2)
        for blk in self.seq:
            f = f + blk(f)
        return self.fc(f).permute(0, 2, 1)
