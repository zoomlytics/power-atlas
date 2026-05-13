import subprocess
import sys

cmd = [sys.executable, "-m", "pytest", "tests/test_backend_api_consumer.py::test_reusable_core_domain_pack_runs_from_outside_repo_when_installed", "-v"]
try:
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    print("Test passed!")
    print(result.stdout)
except subprocess.CalledProcessError as e:
    print("Test failed!")
    print("STDOUT:")
    print(e.stdout)
    print("STDERR:")
    print(e.stderr)
