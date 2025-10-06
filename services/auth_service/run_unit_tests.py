
import subprocess
import sys
from pathlib import Path

def run_unit_tests():
    """unit-тестирование с помощью pytest"""
    
    print("=" * 60)
    print("ЗАПУСК МОДУЛЬНЫХ ТЕСТОВ")
    print("=" * 60)
    print()
    
    test_dir = Path(__file__).parent / "tests" / "unit"
    
    # запуск pytest
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_dir),
        "-v",                          
        "--tb=short",                  
        "--color=yes",                 
        "-p", "no:warnings",           
    ]
    
    print(f"Директория с тестами: {test_dir}")
    print(f"Команда: {' '.join(cmd)}")
    print()
    print("-" * 60)
    
    try:
        result = subprocess.run(cmd, check=False)
        
        print()
        print("-" * 60)
        
        if result.returncode == 0:
            print("ВСЕ ТЕСТЫ ПРОШЛИ УСПЕШНО!")
            print()
            print("Для подробной статистики покрытия запустите:")
            print(f"   pytest {test_dir} --cov=app --cov-report=html")
            return True
        else:
            print("НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
            print()
            print("Проверьте вывод выше для деталей")
            return False
            
    except FileNotFoundError:
        print("pytest не установлен")
        print()
        return False
    except Exception as e:
        print(f"НЕПРЕДВИДЕННАЯ ОШИБКА: {e}")
        return False


if __name__ == "__main__":
    success = run_unit_tests()
    sys.exit(0 if success else 1)