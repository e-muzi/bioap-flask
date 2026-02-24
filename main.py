"""Application entry point. Creates the app, initializes DB, and runs the server."""
from app import create_app
from app.extensions import db
from app.services import seed_defaults, ensure_scientific_data_column

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_scientific_data_column()
        seed_defaults()
    app.run(port=3000, debug=False)
