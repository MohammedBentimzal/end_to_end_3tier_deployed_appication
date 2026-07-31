from flask import Flask, render_template, request, redirect
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# -------------------------------
# PostgreSQL Configuration
# -------------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "postgresql://postgres:1234@10.0.3.10:5432/postgresDB"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# -------------------------------
# Database Models
# -------------------------------

class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship(
        "Task",
        backref="project",
        cascade="all, delete",
        lazy=True
    )


class Task(db.Model):
    __tablename__ = "tasks"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    completed = db.Column(db.Boolean, default=False)

    project_id = db.Column(
        db.Integer,
        db.ForeignKey("projects.id"),
        nullable=False
    )


# -------------------------------
# Create tables automatically
# -------------------------------

with app.app_context():
    db.create_all()

# -------------------------------
# Home Page
# -------------------------------

@app.route("/")
def home():

    projects = Project.query.order_by(Project.id).all()
    tasks = Task.query.order_by(Task.id).all()

    return render_template(
        "index.html",
        projects=projects,
        tasks=tasks
    )


# -------------------------------
# Create Project
# -------------------------------

@app.route("/add_project", methods=["POST"])
def add_project():

    name = request.form["project_name"]

    if name.strip():

        project = Project(name=name)

        db.session.add(project)
        db.session.commit()

    return redirect("/")


# -------------------------------
# Create Task
# -------------------------------

@app.route("/add_task", methods=["POST"])
def add_task():

    title = request.form["task_title"]
    project_id = request.form["project_id"]

    if title.strip():

        task = Task(
            title=title,
            project_id=project_id
        )

        db.session.add(task)
        db.session.commit()

    return redirect("/")


# -------------------------------
# Complete Task
# -------------------------------

@app.route("/complete/<int:id>")
def complete(id):

    task = Task.query.get_or_404(id)

    task.completed = True

    db.session.commit()

    return redirect("/")


# -------------------------------
# Health Check
# -------------------------------

@app.route("/health")
def health():

    try:
        db.session.execute(db.text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected"
        }

    except Exception as e:

        return {
            "status": "unhealthy",
            "error": str(e)
        }, 500


# -------------------------------
# API Information
# -------------------------------

@app.route("/api/info")
def info():

    return {
        "application": "Task Manager",
        "backend": "Flask",
        "database": "PostgreSQL",
        "cloud": "AWS EC2"
    }


# -------------------------------

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )