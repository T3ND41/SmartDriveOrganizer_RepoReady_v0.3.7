$ErrorActionPreference = 'Stop'
python -m pip install --upgrade pip
python -m pip install -e '.[content,build]'
python -m unittest discover -s tests -v
pyinstaller --noconfirm --clean --onefile --windowed --name SmartDriveOrganizer --collect-submodules smart_drive_organizer --hidden-import pypdf --hidden-import openpyxl --hidden-import pptx --add-data 'config;config' --add-data 'smart_drive_organizer/assets;smart_drive_organizer/assets' run.py
Write-Host 'Built dist\SmartDriveOrganizer.exe' -ForegroundColor Green
