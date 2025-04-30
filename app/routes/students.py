from flask import Blueprint, render_template, flash, redirect, url_for, request, make_response
from db import get_db_connection, release_db_connection
from gpa_calculator import calculate_gpa
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

students_bp = Blueprint('students', __name__, url_prefix='/students')

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
        department_filter = request.args.get('department', '')
        major_filter = request.args.get('major', '')
        page = int(request.args.get('page', 1))
        per_page = 30

        cur = conn.cursor()

        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
        majors = [row[0] for row in cur.fetchall()]

        query = """
            SELECT s.student_id, s.name, s.email, s.major, d.department_name 
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE 1=1
        """
        params = []

        if search_query:
            query += " AND (s.student_id::text ILIKE %s OR s.name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        if department_filter:
            query += " AND s.department_id = %s"
            params.append(department_filter)

        if major_filter:
            query += " AND s.major = %s"
            params.append(major_filter)

        query += " ORDER BY s.student_id"

        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'students.html',
            students=students,
            departments=departments,
            majors=majors,
            search_query=search_query,
            department_filter=department_filter,
            major_filter=major_filter,
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


@students_bp.route('/<int:id>/download_report')
def download_report(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # Get student information
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

        # Get course information
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

        # Create PDF report
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = styles['Heading1']
        title_style.alignment = 1  # Center alignment
        elements.append(Paragraph(f"Student Report: {student[1]}", title_style))
        elements.append(Spacer(1, 0.25 * inch))

        # Student Information
        info_data = [
            ['Student ID:', str(student[0])],
            ['Name:', student[1]],
            ['Age:', str(student[2])],
            ['Email:', student[3]],
            ['Major:', student[4]],
            ['Department:', student[5]],
        ]

        if gpa:
            info_data.append(['GPA:', f"{gpa:.2f}"])
            info_data.append(['Completed Credits:', str(completed_credits)])
            info_data.append(['Current Credits:', str(current_credits)])

        info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (1, -3), (1, -1), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.25 * inch))

        # Current Courses
        if current_courses:
            elements.append(Paragraph("Currently Enrolled Courses", styles['Heading2']))
            elements.append(Spacer(1, 0.1 * inch))

            current_table_data = [['Course Name', 'Credits', 'Semester', 'Instructor']]
            for course in current_courses:
                current_table_data.append([
                    course[0],
                    str(course[1]),
                    course[2],
                    course[4] or "Unassigned"
                ])

            current_table = Table(current_table_data, colWidths=[2.5 * inch, 1 * inch, 1.5 * inch, 2 * inch])
            current_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(current_table)
            elements.append(Spacer(1, 0.25 * inch))

        # Completed Courses
        if completed_courses:
            elements.append(Paragraph("Completed Courses", styles['Heading2']))
            elements.append(Spacer(1, 0.1 * inch))

            completed_table_data = [['Course Name', 'Credits', 'Semester', 'Grade', 'Instructor']]
            for course in completed_courses:
                completed_table_data.append([
                    course[0],
                    str(course[1]),
                    course[2],
                    course[3],
                    course[4] or "Unassigned"
                ])

            completed_table = Table(completed_table_data,
                                    colWidths=[2 * inch, 0.75 * inch, 1.25 * inch, 0.75 * inch, 2 * inch])
            completed_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(completed_table)

        # Build PDF
        doc.build(elements)

        # Create response
        pdf_data = buffer.getvalue()
        buffer.close()

        response = make_response(pdf_data)
        response.headers['Content-Disposition'] = f'attachment; filename=student_report_{student[0]}.pdf'
        response.mimetype = 'application/pdf'

        return response
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        flash(f"Error generating report: {str(e)}", "danger")
        return redirect(url_for('students.student_detail', id=id))
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
        major_filter = request.args.get('major', '')
        page = int(request.args.get('page', 1))
        per_page = 30

        cur = conn.cursor()

        # Get departments for the filter dropdown
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # Get distinct majors for the filter dropdown
        cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
        majors = [row[0] for row in cur.fetchall()]

        query = """
            SELECT s.student_id, s.name, s.age, s.email, s.major, d.department_name, s.department_id
            FROM students s
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE 1=1
        """
        params = []

        if search_query:
            query += " AND (s.student_id::text ILIKE %s OR s.name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        if department_filter:
            query += " AND s.department_id = %s"
            params.append(department_filter)

        if major_filter:
            query += " AND s.major = %s"
            params.append(major_filter)

        query += " ORDER BY s.student_id"

        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cur.execute(query, params)
        students = cur.fetchall()

        cur.close()
        return render_template(
            'edit_student.html',
            students=students,
            departments=departments,
            majors=majors,
            search_query=search_query,
            department_filter=department_filter,
            major_filter=major_filter,
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

            if student_id:
                cur.execute("SELECT COUNT(*) FROM students WHERE student_id = %s", (student_id,))
                if cur.fetchone()[0] > 0:
                    cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                    departments = cur.fetchall()

                    cur.execute("SELECT DISTINCT major FROM students ORDER BY major")
                    majors = [row[0] for row in cur.fetchall()]

                    cur.close()
                    return render_template('add_student.html',
                                           message="Student ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           departments=departments,
                                           majors=majors)

                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (student_id, name, age, email, major, department_id))
            else:
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

                cur.execute("""
                    INSERT INTO students (student_id, name, age, email, major, department_id)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (next_id, name, age, email, major, department_id))
                student_id = next_id

            conn.commit()
            flash("Student added successfully!", "success")
            return redirect(url_for('students.edit_enrollments', student_id=student_id))
        cur = conn.cursor()

        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

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

        cur.execute("""
            SELECT COUNT(*) FROM students 
            WHERE email = %s AND student_id != %s
        """, (email, id))

        if cur.fetchone()[0] > 0:
            flash("Email already exists for another student", "danger")
            return redirect(url_for('students.edit_student', id=id))

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

        cur.execute("DELETE FROM enrollments WHERE student_id = %s", (id,))

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

@students_bp.route('/enrollments/<int:student_id>', methods=['GET'])
def edit_enrollments(student_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

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

        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            ORDER BY d.department_name, c.course_name
        """)
        available_courses = cur.fetchall()

        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025']

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

        cur = conn.cursor()

        cur.execute("""
            SELECT s.student_id, s.name
            FROM students s
            WHERE s.student_id = %s
        """, (student_id,))
        student = cur.fetchone()

        if not student:
            flash("Student not found", "danger")
            return redirect(url_for('students.edit_students'))

        # Get all courses with their departments
        cur.execute("""
            SELECT c.course_id, c.course_name, d.department_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            ORDER BY d.department_name, c.course_name
        """)
        courses = cur.fetchall()

        # In the add_enrollment function
        # Get available semesters for each course
        course_semesters = {}
        for course in courses:
            course_id = str(course[0])

            # Only look for semesters that are explicitly offered for this course
            # (where there's a NULL student_id entry)
            # Get all distinct semesters that this course is offered in
            cur.execute("""
                SELECT DISTINCT semester 
                FROM enrollments 
                WHERE course_id = %s AND semester IS NOT NULL
                UNION
                SELECT DISTINCT semester 
                FROM enrollments 
                WHERE course_id = %s AND student_id IS NULL
                ORDER BY semester
            """, (course[0], course[0]))

            semesters = [row[0] for row in cur.fetchall()]
            course_semesters[course_id] = semesters

        grades = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']

        cur.close()
        return render_template(
            'add_enrollment.html',
            student=student,
            courses=courses,
            course_semesters=course_semesters,
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


@students_bp.route('/enrollment/delete/<int:enrollment_id>', methods=['POST'])
def delete_enrollment(enrollment_id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        cur.execute("SELECT student_id FROM enrollments WHERE enrollment_id = %s", (enrollment_id,))
        result = cur.fetchone()

        if not result:
            flash("Enrollment not found", "danger")
            return redirect(url_for('students.edit_students'))

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


