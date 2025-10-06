

import sys
from pathlib import Path

# Добавляем путь к приложению
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Включаем поддержку asyncio для pytest
pytest_plugins = ('pytest_asyncio',)