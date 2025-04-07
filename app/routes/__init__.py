from routes.students import students_bp
from routes.courses import courses_bp
from routes.departments import departments_bp
from routes.instructors import instructors_bp
from routes.enrollments import enrollments_bp

def register_blueprints(app):
    app.register_blueprint(students_bp)
    app.register_blueprint(courses_bp)
    app.register_blueprint(departments_bp)
    app.register_blueprint(instructors_bp)
    app.register_blueprint(enrollments_bp)