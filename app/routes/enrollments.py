from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection

enrollments_bp = Blueprint('enrollments', __name__, url_prefix='/enrollments')


@enrollments_bp.route('/')
def list_enrollments():
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                e.enrollment_id,
                s.student_id,
                s.name as student_name,
                c.course_id,
                c.course_name,
                e.semester,
                e.grade,
                i.instructor_id,
                i.name as instructor_name,
                d.department_name
            FROM 
                enrollments e
            JOIN 
                students s ON e.student_id = s.student_id
            JOIN 
                courses c ON e.course_id = c.course_id
            LEFT JOIN 
                instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN 
                departments d ON c.department_id = d.department_id
            ORDER BY 
                s.student_id,
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
        """)

        enrollment_rows = cur.fetchall()
        students_dict = {}

        for row in enrollment_rows:
            student_id = row[1]
            enrollment = {
                'enrollment_id': row[0],
                'course_id': row[3],
                'course_name': row[4],
                'semester': row[5],
                'grade': row[6],
                'instructor_id': row[7],
                'instructor_name': row[8],
                'department_name': row[9]
            }

            if student_id not in students_dict:
                students_dict[student_id] = {
                    'student_id': student_id,
                    'student_name': row[2],
                    'enrollments': [],
                    'total_courses': 0,
                    'current_courses': 0
                }

            students_dict[student_id]['enrollments'].append(enrollment)
            students_dict[student_id]['total_courses'] += 1

            if row[5] == 'Fall 2025':
                students_dict[student_id]['current_courses'] += 1

        students = list(students_dict.values())
        students.sort(key=lambda x: x['student_id'])

        cur.close()
        return render_template('enrollments_list.html', students=students)
    finally:
        release_db_connection(conn)


@enrollments_bp.route('/add', methods=['GET', 'POST'])
def add_enrollment():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            student_id = request.form['student_id']
            course_id = request.form['course_id']
            semester = request.form['semester']
            grade = request.form.get('grade', None)

            if grade == '':
                grade = None

            cur = conn.cursor()

            cur.execute("""
                SELECT COUNT(*) FROM enrollments 
                WHERE student_id = %s AND course_id = %s AND semester = %s
            """, (student_id, course_id, semester))

            if cur.fetchone()[0] > 0:
                flash("Enrollment already exists for this student, course, and semester", "danger")
                return redirect(url_for('enrollments.add_enrollment'))

            # Add enrollment
            cur.execute("""
                INSERT INTO enrollments (student_id, course_id, semester, grade)
                VALUES (%s, %s, %s, %s)
            """, (student_id, course_id, semester, grade))

            conn.commit()
            flash("Enrollment added successfully", "success")
            return redirect(url_for('students.edit_enrollments', student_id=student_id))

        cur = conn.cursor()

        cur.execute("SELECT student_id, name FROM students ORDER BY name")
        students = cur.fetchall()

        # Get available courses
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            ORDER BY d.department_name, c.course_name
        """)
        courses = cur.fetchall()

        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'add_enrollment_all.html',  # You'll need to create this template
            students=students,
            courses=courses,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('enrollments.list_enrollments'))
    finally:
        release_db_connection(conn)


@enrollments_bp.route('/edit/<int:enrollment_id>', methods=['GET', 'POST'])
def edit_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT e.student_id, e.course_id, e.semester, e.grade,
                   s.name as student_name, c.course_name
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            JOIN courses c ON e.course_id = c.course_id
            WHERE e.enrollment_id = %s
        """, (enrollment_id,))
        enrollment = cur.fetchone()

        if not enrollment:
            flash("Enrollment not found", "danger")
            return redirect(url_for('enrollments.list_enrollments'))

        student_id = enrollment[0]

        if request.method == 'POST':
            semester = request.form['semester']
            grade = request.form.get('grade', None)

            if grade == '':
                grade = None

            # Update enrollment
            cur.execute("""
                UPDATE enrollments
                SET semester = %s, grade = %s
                WHERE enrollment_id = %s
            """, (semester, grade, enrollment_id))

            conn.commit()
            flash("Enrollment updated successfully", "success")
            return redirect(url_for('students.edit_enrollments', student_id=student_id))

        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'edit_enrollment.html',
            enrollment=enrollment,
            enrollment_id=enrollment_id,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('students.edit_enrollments', student_id=student_id))
    finally:
        release_db_connection(conn)


@enrollments_bp.route('/delete/<int:enrollment_id>', methods=['POST'])
def delete_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT student_id FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))
        result = cur.fetchone()

        if not result:
            flash("Enrollment not found", "danger")
            return redirect(url_for('enrollments.list_enrollments'))

        student_id = result[0]

        cur.execute("DELETE FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))

        conn.commit()
        flash("Enrollment deleted successfully", "success")
        return redirect(url_for('students.edit_enrollments', student_id=student_id))
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('students.edit_enrollments', student_id=student_id))
    finally:
        release_db_connection(conn)

@enrollments_bp.route('/update/<int:enrollment_id>', methods=['GET', 'POST'])
def update_enrollment(enrollment_id):
    return edit_enrollment(enrollment_id)

@enrollments_bp.route('/manage')
def manage_enrollments():
    return render_template('manage_enrollments.html')