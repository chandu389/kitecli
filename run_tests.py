import sys
import unittest

if __name__ == "__main__":
    print("🪁 Running KiteCLI Test Suite offline (No actual orders will be placed)...")
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
