from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection

instructors_bp = Blueprint('instructors', __name__, url_prefix='/instructors')


@instructors_bp.route('/')
def list_instructors():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name
            FROM instructors i
            LEFT JOIN departments d ON i.department_id = d.department_id
            ORDER BY i.name
        """)
        instructors = cur.fetchall()
        cur.close()
        return render_template('instructors_list.html', instructors=instructors)
    finally:
        release_db_connection(conn)


@instructors_bp.route('/<int:id>')
def instructor_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name, d.department_id
            FROM instructors i
            LEFT JOIN departments d ON i.department_id = d.department_id
            WHERE i.instructor_id = %s
        """, (id,))
        instructor = cur.fetchone()

        if instructor is None:
            flash("Instructor not found", "danger")
            return redirect(url_for('instructors.list_instructors'))

        cur.execute("""
            WITH enrollment_counts AS (
                SELECT course_id, semester, COUNT(*) as enrolled_count
                FROM enrollments
                GROUP BY course_id, semester
            )
            SELECT c.course_id, c.course_name, c.credits, d.department_name, 
                   e.semester, COALESCE(e.enrolled_count, 0) as enrolled_count
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN enrollment_counts e ON c.course_id = e.course_id AND e.semester IS NOT NULL
            WHERE c.instructor_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    WHEN e.semester = 'Spring 2024' THEN 5
                    WHEN e.semester = 'Winter 2024' THEN 6
                    WHEN e.semester = 'Fall 2023' THEN 7
                    ELSE 8
                END,
                c.course_name
        """, (id,))

        instructor_courses = {}
        for row in cur.fetchall():
            course_info = {
                'course_id': row[0],
                'course_name': row[1],
                'credits': row[2],
                'department_name': row[3],
                'enrolled_count': row[5]
            }

            semester = row[4] or 'Unscheduled'

            if semester not in instructor_courses:
                instructor_courses[semester] = []

            instructor_courses[semester].append(course_info)

        cur.close()
        return render_template(
            'instructors_details.html',
            instructor=instructor,
            instructor_courses=instructor_courses
        )
    finally:
        release_db_connection(conn)


@instructors_bp.route('/manage')
def manage_instructors():
    # You can create this view in the future
    return render_template('manage_instructors.html')


@instructors_bp.route('/add', methods=['GET', 'POST'])
def add_instructor():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            department_id = request.form.get('department_id')

            if not department_id:
                department_id = None

            cur = conn.cursor()

            cur.execute("SELECT COUNT(*) FROM instructors WHERE email = %s", (email,))
            if cur.fetchone()[0] > 0:
                flash("An instructor with this email already exists", "danger")
                cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                departments = cur.fetchall()
                cur.close()
                return render_template('add_instructor.html', departments=departments)

            cur.execute("""
                INSERT INTO instructors (name, email, department_id)
                VALUES (%s, %s, %s)
                RETURNING instructor_id
            """, (name, email, department_id))

            instructor_id = cur.fetchone()[0]
            conn.commit()

            flash("Instructor added successfully!", "success")
            return redirect(url_for('instructors.instructor_detail', id=instructor_id))

        cur = conn.cursor()
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()
        cur.close()

        return render_template('add_instructor.html', departments=departments)
    except Exception as e:
        conn.rollback()
        flash(f"Error adding instructor: {str(e)}", "danger")
        return redirect(url_for('instructors.manage_instructors'))
    finally:
        release_db_connection(conn)


@instructors_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_instructor(id):
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            name = request.form['name']
            email = request.form['email']
            department_id = request.form.get('department_id')

            if not department_id:
                department_id = None

            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) FROM instructors 
                WHERE email = %s AND instructor_id != %s
            """, (email, id))

            if cur.fetchone()[0] > 0:
                flash("This email is already used by another instructor", "danger")
                return redirect(url_for('instructors.edit_instructor', id=id))

            cur.execute("""
                UPDATE instructors
                SET name = %s, email = %s, department_id = %s
                WHERE instructor_id = %s
            """, (name, email, department_id, id))

            conn.commit()
            flash("Instructor updated successfully", "success")
            return redirect(url_for('instructors.instructor_detail', id=id))

        cur = conn.cursor()

        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, i.department_id, d.department_name
            FROM instructors i
            LEFT JOIN departments d ON i.department_id = d.department_id
            WHERE i.instructor_id = %s
        """, (id,))

        instructor = cur.fetchone()

        if not instructor:
            flash("Instructor not found", "danger")
            return redirect(url_for('instructors.list_instructors'))

        # Get all departments for dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        cur.close()
        return render_template(
            'edit_instructor.html',
            instructor=instructor,
            departments=departments
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error updating instructor: {str(e)}", "danger")
        return redirect(url_for('instructors.instructor_detail', id=id))
    finally:
        release_db_connection(conn)


@instructors_bp.route('/delete/<int:id>', methods=['POST'])
def delete_instructor(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT COUNT(*) FROM courses WHERE instructor_id = %s", (id,))
        if cur.fetchone()[0] > 0:
            cur.execute("UPDATE courses SET instructor_id = NULL WHERE instructor_id = %s", (id,))

        cur.execute("DELETE FROM instructors WHERE instructor_id = %s", (id,))

        conn.commit()
        flash("Instructor deleted successfully", "success")
        return redirect(url_for('instructors.list_instructors'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting instructor: {str(e)}", "danger")
        return redirect(url_for('instructors.instructor_detail', id=id))
    finally:
        release_db_connection(conn)