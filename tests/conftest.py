import os, sys, tempfile
from pathlib import Path

# Ortam, backend.app import edilmeden ÖNCE hazırlanır.
os.environ.setdefault("TORQPRO_SECRET_KEY", "x" * 64)
_tmpdir = tempfile.mkdtemp(prefix="torqpro-test-")
os.environ["TORQPRO_DB_PATH"] = str(Path(_tmpdir) / "torqpro_test.db")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import app as _appmod  # noqa: E402

# TestClient with-bloğu kullanılmadığında lifespan tetiklenmez;
# temiz ortamda şema garantisi burada verilir.
_appmod.migrate()
