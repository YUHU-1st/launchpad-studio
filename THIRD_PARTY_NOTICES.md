# Third-party notices

Launchpad Studio uses open-source Python packages listed in `requirements.txt`; their respective licenses apply.

The optional bundled temperature helper uses [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor), distributed under the Mozilla Public License 2.0. The helper project source is available in `tools/TemperatureHelper`, and the upstream source is available from the linked project.

Weather and geocoding data are provided by [Open-Meteo](https://open-meteo.com/) under its published terms and attribution requirements.

Novation and Launchpad are trademarks of Focusrite Audio Engineering Ltd. This independent project is not affiliated with or endorsed by Novation.

## VJ runtime

Launchpad Studio's application code and procedural VJ shaders are MIT licensed.
No third-party VJ footage, preset, logo or texture is redistributed.

- **PySide6 / Qt 6**: dynamically linked Qt libraries are supplied under LGPLv3.
  The LGPLv3/GPLv3 license texts are included in `licenses/` in this distribution.
  Source and build instructions are available from
  https://download.qt.io/archive/qt/6.11/6.11.2/single/ and
  https://code.qt.io/pyside/pyside-setup.git/?h=v6.11.2.
  PySide6 6.11.2 is installed from the unmodified official PyPI wheel and pinned
  in the project's `requirements.txt`. This application does not restrict
  replacement of the shared Qt libraries or reverse engineering for debugging
  modifications to those libraries. Keep this notice and the Qt license texts
  when redistributing the Windows package.
- **ModernGL / glcontext**: MIT license. https://github.com/moderngl/moderngl
  and https://github.com/moderngl/glcontext.

The installed package metadata and license files identify the other bundled
Python dependencies. TemperatureHelper includes LibreHardwareMonitor and its
dependencies under their respective upstream licenses.

Visual design references only (not copied assets):
https://github.com/jberg/butterchurn and https://resolume.com/footage.
