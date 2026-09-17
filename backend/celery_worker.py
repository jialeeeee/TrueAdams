from app import create_app, tasks  # noqa: F401  (import registers Celery tasks)
from app.extensions import celery

flask_app = create_app()
flask_app.app_context().push()
