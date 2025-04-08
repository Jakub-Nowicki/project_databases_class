from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection
from gpa_calculator import calculate_gpa

# Create a Blueprint for student routes
students_bp = Blueprint('students', __name__, url_prefix='/students')

# Helper function to get all departments for dropdowns
def get_all_departments():
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()
        cur.close()
        return departments
    finally:
        release_db_connection(conn)


@students_bp.route('/')
def list_students():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Students per page

        cur = conn.cursor()

        # Base query
        query = """
            SELECT student_id, name
            FROM students
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (student_id::text ILIKE %s OR name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        # Add ordering
        query += " ORDER BY student_id"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'students.html',
            students=students,
            search_query=search_query,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)


@students_bp.route('/<int:id>')
def student_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (id,))
        student = cur.fetchone()

        if student is None:
            flash("Student not found", "danger")
            return redirect(url_for('students.list_students'))

        cur.execute("""
            SELECT c.course_name, c.credits, e.semester, e.grade, i.name as instructor_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE e.student_id = %s
            ORDER BY e.semester DESC
        """, (id,))
        all_courses = cur.fetchall()

        current_courses = []
        completed_courses = []
        current_credits = 0

        for course in all_courses:
            credits = course[1] or 0

            if course[3] is None:
                current_courses.append(course)
                current_credits += credits
            else:
                completed_courses.append(course)

        gpa, completed_credits, gpa_points = calculate_gpa(all_courses)

        cur.close()
        return render_template(
            'student_detail.html',
            student=student,
            current_courses=current_courses,
            completed_courses=completed_courses,
            gpa=gpa,
            completed_credits=completed_credits,
            current_credits=current_credits
        )
    finally:
        release_db_connection(conn)


@students_bp.route('/manage')
def manage_students():
    return render_template('manage_students.html')


@students_bp.route('/edit')
def edit_students():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        department_filter = request.args.get('department', '')
        page = int(request.args.get('page', 1))
        per_page = 30  # Updated to 30 students per page as requested

        cur = conn.cursor()

        # Get departments for filter dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Base query
        query = """
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name, s.department_id
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE 1=1
        """
        params = []

        # Add search condition if search query exists
        if search_query:
            query += " AND (s.student_id::text ILIKE %s OR s.name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        # Add department filter if selected
        if department_filter:
            query += " AND s.department_id = %s"
            params.append(department_filter)

        # Add ordering by student ID instead of name
        query += " ORDER BY s.student_id"

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # Calculate pagination
        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # Add pagination to the query
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        # Execute final query
        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'edit_student.html',
            students=students,
            departments=departments,
            search_query=search_query,
            department_filter=department_filter,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)


@students_bp.route('/edit/<int:id>', methods=['GET'])
def edit_student(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student details
        cur.execute("""
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name, s.department_id
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (id,))
        student = cur.fetchone()

        if student is None:
            flash("Student not found", "danger")
            return redirect(url_for('students.edit_students'))

        # Get student enrollments
        cur.execute("""
            SELECT c.course_name, e.semester, e.grade, i.name as instructor_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE e.student_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    ELSE 5
                END,
                c.course_name
        """, (id,))
        enrollments = cur.fetchall()

        # Get departments for dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        cur.close()
        return render_template(
            'edit_idnividual.html',  # Use the individual edit template file
            student=student,
            enrollments=enrollments,
            departments=departments
        )
    finally:
        release_db_connection(conn)


@students_bp.route('/add', methods=['GET', 'POST'])
def add_student():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            name = request.form['name']
            age = request.form['age']
            email = request.form['email']
            major = request.form['major']
            department_id = request.form['department_id']
            student_id = request.form.get('student_id', '').strip()

            cur = conn.cursor()

            # Check if email already exists
            cur.execute("SELECT COUNT(*) FROM students WHERE email = %s", (email,))
            if cur.fetchone()[0] > 0:
                # Get departments for dropdown
                cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                departments = cur.fetchall()

                # Get existing majors for dropdown
                cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
                majors = [row[0] for row in cur.fetchall()]

                cur.close()
                return render_template('add_student.html',
                                       message="Email already exists in the database.",
                                       message_type="danger",
                                       departments=departments,
                                       majors=majors)

            # Insert new student
            if student_id:
                # Check if ID already exists
                cur.execute("SELECT COUNT(*) FROM students WHERE student_id = %s", (student_id,))
                if cur.fetchone()[0] > 0:
                    # Get departments for dropdown
                    cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                    departments = cur.fetchall()

                    # Get existing majors for dropdown
                    cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
                    majors = [row[0] for row in cur.fetchall()]

                    cur.close()
                    return render_template('add_student.html',
                                           message="Student ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           departments=departments,
                                           majors=majors)

                # Insert with provided ID
                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (student_id, name, age, email, major, department_id))
            else:
                # Find the smallest available ID (this will reuse deleted IDs)
                cur.execute("""
                    SELECT MIN(t.student_id + 1) AS next_id 
                    FROM students t 
                    WHERE NOT EXISTS (
                        SELECT 1 FROM students t2 
                        WHERE t2.student_id = t.student_id + 1
                    )
                    UNION
                    SELECT 1
                    WHERE NOT EXISTS (SELECT 1 FROM students WHERE student_id = 1)
                    ORDER BY next_id
                    LIMIT 1
                """)
                next_id = cur.fetchone()[0]

                # Insert student with the next available ID
                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (next_id, name, age, email, major, department_id))
                student_id = next_id

            conn.commit()
            flash("Student added successfully!", "success")
            return redirect(url_for('students.edit_student', id=student_id))

        # GET request - show form
        cur = conn.cursor()

        # Get departments for dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Get existing majors for dropdown
        cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
        majors = [row[0] for row in cur.fetchall()]

        cur.close()
        return render_template('add_student.html', departments=departments, majors=majors)
    except Exception as e:
        conn.rollback()
        flash(f"Error adding student: {str(e)}", "danger")
        return redirect(url_for('students.manage_students'))
    finally:
        release_db_connection(conn)


@students_bp.route('/update/<int:id>', methods=['POST'])
def update_student(id):
    conn = get_db_connection()
    try:
        name = request.form['name']
        age = request.form['age']
        email = request.form['email']
        major = request.form['major']
        department_id = request.form['department_id']

        cur = conn.cursor()

        # Check if email already exists for another student
        cur.execute("""
            SELECT COUNT(*) FROM students 
            WHERE email = %s AND student_id != %s
        """, (email, id))

        if cur.fetchone()[0] > 0:
            flash("Email already exists for another student", "danger")
            return redirect(url_for('students.edit_student', id=id))

        # Update student record
        cur.execute("""
            UPDATE students
            SET name = %s, age = %s, email = %s, major = %s, department_id = %s
            WHERE student_id = %s
        """, (name, age, email, major, department_id, id))

        conn.commit()
        flash("Student updated successfully", "success")
        return redirect(url_for('students.edit_student', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating student: {str(e)}", "danger")
        return redirect(url_for('students.edit_student', id=id))
    finally:
        release_db_connection(conn)


@students_bp.route('/delete/<int:id>', methods=['POST'])
def delete_student(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Delete student enrollments first (due to foreign key constraint)
        cur.execute("DELETE FROM enrollments WHERE student_id = %s", (id,))

        # Delete student record
        cur.execute("DELETE FROM students WHERE student_id = %s", (id,))

        conn.commit()
        flash("Student deleted successfully", "success")
        return redirect(url_for('students.edit_students'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting student: {str(e)}", "danger")
        return redirect(url_for('students.edit_student', id=id))
    finally:
        release_db_connection(conn)


# Student enrollment routes
@students_bp.route('/enrollments/<int:student_id>', methods=['GET'])
def edit_enrollments(student_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student info
        cur.execute("""
            SELECT s.student_id, s.name, s.email, d.department_name
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE s.student_id = %s
        """, (student_id,))
        student = cur.fetchone()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for('students.edit_students'))

        # Get student enrollments
        cur.execute("""
            SELECT e.enrollment_id, c.course_id, c.course_name, e.semester, e.grade,
                  i.name as instructor_name, d.department_name
            FROM enrollments e
            JOIN courses c ON e.course_id = c.course_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            LEFT JOIN departments d ON c.department_id = d.department_id
            WHERE e.student_id = %s
            ORDER BY 
                CASE 
                    WHEN e.semester = 'Fall 2025' THEN 1
                    WHEN e.semester = 'Spring 2025' THEN 2
                    WHEN e.semester = 'Winter 2025' THEN 3
                    WHEN e.semester = 'Fall 2024' THEN 4
                    ELSE 5
                END,
                c.course_name
        """, (student_id,))
        enrollments = cur.fetchall()

        # Get available courses for adding new enrollments
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            ORDER BY d.department_name, c.course_name
        """)
        available_courses = cur.fetchall()

        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'edit_enrollments.html',
            student=student,
            enrollments=enrollments,
            available_courses=available_courses,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('students.edit_student', id=student_id))
    finally:
        release_db_connection(conn)


@students_bp.route('/enrollment/add/<int:student_id>', methods=['GET', 'POST'])
def add_enrollment(student_id):
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            course_id = request.form['course_id']
            semester = request.form['semester']
            grade = request.form.get('grade', None)
            if grade == '':
                grade = None

            # Check if enrollment already exists
            cur = conn.cursor()
            cur.execute("""
                SELECT COUNT(*) FROM enrollments 
                WHERE student_id = %s AND course_id = %s AND semester = %s
            """, (student_id, course_id, semester))

            if cur.fetchone()[0] > 0:
                flash("Enrollment already exists for this student, course, and semester", "danger")
                return redirect(url_for('students.add_enrollment', student_id=student_id))

            # Add enrollment
            cur.execute("""
                INSERT INTO enrollments (student_id, course_id, semester, grade)
                VALUES (%s, %s, %s, %s)
            """, (student_id, course_id, semester, grade))

            conn.commit()
            flash("Enrollment added successfully", "success")
            return redirect(url_for('students.edit_enrollments', student_id=student_id))

        # GET request - show form
        cur = conn.cursor()

        # Get student info
        cur.execute("""
            SELECT s.student_id, s.name
            FROM students s
            WHERE s.student_id = %s
        """, (student_id,))
        student = cur.fetchone()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for('students.edit_students'))

        # Get available courses
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            ORDER BY d.department_name, c.course_name
        """)
        courses = cur.fetchall()

        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'add_enrollment.html',
            student=student,
            courses=courses,
            semesters=semesters,
            grades=grades
        )
    except Exception as e:
        conn.rollback()
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('students.edit_student', id=student_id))
    finally:
        release_db_connection(conn)


@students_bp.route('/enrollment/edit/<int:enrollment_id>', methods=['GET', 'POST'])
def update_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get enrollment details first (needed for both GET and POST)
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
            return redirect(url_for('students.edit_students'))

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

        # GET request - show form
        # Get available semesters
        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

        # Get grade options
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


@students_bp.route('/enrollment/delete/<int:enrollment_id>', methods=['POST'])
def delete_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student_id first for redirect
        cur.execute("SELECT student_id FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))
        result = cur.fetchone()

        if not result:
            flash("Enrollment not found", "danger")
            return redirect(url_for('students.edit_students'))

        student_id = result[0]

        # Delete enrollment
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