from dotenv import load_dotenv
from flask import Flask

from .auth.routes import auth_bp
from .config import Config
from .events.routes import events_bp
from .extensions import celery, cors, db, jwt
from .registrations.routes import registrations_bp
from .resources.routes import resources_bp
from .venues.routes import venues_bp

load_dotenv()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    cors.init_app(app)
    celery.conf.update(
        broker_url=app.config["CELERY_BROKER_URL"],
        result_backend=app.config["CELERY_RESULT_BACKEND"],
    )

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(events_bp, url_prefix="/api/events")
    app.register_blueprint(venues_bp, url_prefix="/api/venues")
    app.register_blueprint(resources_bp, url_prefix="/api/resources")
    app.register_blueprint(registrations_bp, url_prefix="/api/registrations")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    return app
