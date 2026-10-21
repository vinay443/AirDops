# Third-party notices

AirDops bundles or depends on the following open-source components.

| Component | License | Use |
|---|---|---|
| [RNNoise](https://github.com/xiph/rnnoise) (Xiph.Org Foundation, Jean-Marc Valin, and the Opus DNN code it includes) | BSD-3-Clause (bundled as `rnnoise-COPYING.txt`) | Neural noise suppression. `rnnoise.dll` is built from pinned Xiph source and model by `scripts/build_rnnoise.py`. |
| [bleak](https://github.com/hbldh/bleak) | MIT | Bluetooth LE scanning |
| [pywinrt](https://github.com/pywinrt/pywinrt) (`winrt-*`) | MIT | Windows Runtime (media sessions, Bluetooth) |
| [pycaw](https://github.com/AndreMiras/pycaw) | MIT | Windows Core Audio interfaces |
| [comtypes](https://github.com/enthought/comtypes) | MIT | COM support |
| [psutil](https://github.com/giampaolo/psutil) | BSD-3-Clause | Install-time dependency of pycaw (not bundled) |
| [python-sounddevice](https://github.com/spatialaudio/python-sounddevice) / PortAudio | MIT | Real-time audio I/O |
| [Qt for Python (PySide6)](https://www.qt.io/qt-for-python) | LGPL-3.0 | User interface. Loaded as unmodified shared libraries; you may replace them (rebuild from this repository with your own PySide6). |
| [Inter](https://rsms.me/inter/) typeface (Rasmus Andersson) | SIL Open Font License 1.1 (bundled as `Inter-OFL.txt`) | UI font |
| [Pillow](https://python-pillow.org) | MIT-CMU (HPND) | Build-time only: writes the .exe icon |
| [pyrnnoise](https://github.com/pengzhendong/pyrnnoise) | Apache-2.0 | CI-only: its old prebuilt RNNoise is the reference for the quality test (not bundled) |
| [PyInstaller](https://pyinstaller.org) bootloader | GPL-2.0 with bootloader exception | Packaging the exe |

RNNoise BSD-3-Clause notice:

    Copyright (c) 2017, Mozilla
    Copyright (c) 2007-2017, Jean-Marc Valin
    Copyright (c) 2005-2017, Xiph.Org Foundation
    Copyright (c) 2003-2004, Mark Borgerding

    Redistribution and use in source and binary forms, with or without
    modification, are permitted provided that the following conditions are met:
    - Redistributions of source code must retain the above copyright notice,
      this list of conditions and the following disclaimer.
    - Redistributions in binary form must reproduce the above copyright notice,
      this list of conditions and the following disclaimer in the documentation
      and/or other materials provided with the distribution.
    - Neither the name of the Xiph.Org Foundation nor the names of its
      contributors may be used to endorse or promote products derived from this
      software without specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
    AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
    IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
    ARE DISCLAIMED. IN NO EVENT SHALL THE FOUNDATION OR CONTRIBUTORS BE LIABLE
    FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
    DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
    SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
    CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
    LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
    OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH
    DAMAGE.
