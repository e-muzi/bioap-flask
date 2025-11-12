from flask import Flask, redirect, url_for, session, render_template_string, render_template, request, flash,jsonify
from flask_session import Session
from flask_bootstrap import Bootstrap5
import os
app = Flask(__name__)

bootstrap = Bootstrap5(app)
app.secret_key = os.urandom(24)  # For session encryption
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_FILE_DIR'] = '/tmp/flask_session'
app.jinja_env.auto_reload = True
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SESSION_COOKIE_NAME'] = "my_session"
Session(app)

@app.route('/')
def index():
    """Renders the main dashboard/index page."""
    # Sample data for the dashboard
    dashboard_data = {
        'active_analyses': 2,
        'recent_alerts': 0
    }
    return render_template('index.html', title="Dashboard", data=dashboard_data)

@app.route('/history')
def history():
    """Renders the analysis history page."""
    # We'll pass an empty list to replicate the "No analysis history"
    # state from your image.
    analysis_history = [] 
    return render_template('history.html', title="Analysis History", history=analysis_history)

@app.route('/settings')
def settings():
    """Renders the settings page."""
    app_settings = {
        'notifications_enabled': True,
        'user_email': 'example@pestiguard.com'
    }
    return render_template('settings.html', title="Settings", settings=app_settings)


    
if __name__ == "__main__":
    app.run(port=3000, debug=False)
    # development
    #app.run(port=3001, debug=False)