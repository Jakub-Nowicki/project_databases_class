from flask import Blueprint, render_template, flash, redirect, url_for, request
from db import get_db_connection, release_db_connection
import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from flask import make_response

courses_bp = Blueprint('courses', __name__, url_prefix='/courses')


@courses_bp.route('/manage')
def manage_courses():
    return render_template('manage_courses.html')

@courses_bp.route('/<int:id>/download_report')
def download_report(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # get course details including department and instructor information
        cur.execute("""
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name, i.email as instructor_email
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE c.course_id = %s
        """, (id,))
        course_data = cur.fetchone()

        if course_data is None:
            flash("Course not found", "danger")
            return redirect(url_for('courses.course_offerings'))

        course = {
            'course_id': course_data[0],
            'course_name': course_data[1],
            'credits': course_data[2],
            'department_name': course_data[5],
            'instructor_name': course_data[6] or "Unassigned",
            'instructor_email': course_data[7] or "N/A"
        }

        # find all semester offerings for this course
        cur.execute("""
            SELECT DISTINCT semester FROM enrollments 
            WHERE course_id = %s
            ORDER BY semester
        """, (id,))
        semesters = [row[0] for row in cur.fetchall()]

        # get all enrolled students with their details
        cur.execute("""
            SELECT e.enrollment_id, s.student_id, s.name AS student_name, 
                   d.department_name, s.major, e.semester, e.grade
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE e.course_id = %s
            ORDER BY e.semester, s.name
        """, (id,))

        enrolled_students = []
        for row in cur.fetchall():
            enrolled_students.append({
                'student_id': row[1],
                'student_name': row[2],
                'department': row[3],
                'major': row[4],
                'semester': row[5],
                'grade': row[6] or "Not Graded"
            })

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        title_style = styles['Heading1']
        title_style.alignment = 1
        elements.append(Paragraph(f"Course Report: {course['course_name']}", title_style))
        elements.append(Spacer(1, 0.25 * inch))

        info_data = [
            ['Course ID:', str(course['course_id'])],
            ['Course Name:', course['course_name']],
            ['Credits:', str(course['credits'])],
            ['Department:', course['department_name']],
            ['Instructor:', course['instructor_name']],
            ['Instructor Email:', course['instructor_email']],
            ['Semesters Offered:', ", ".join(semesters)],
            ['Enrolled Students:', str(len(enrolled_students))],
        ]

        info_table = Table(info_data, colWidths=[2 * inch, 4 * inch])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(info_table)
        elements.append(Spacer(1, 0.25 * inch))

        # group students by semester
        students_by_semester = {}
        for student in enrolled_students:
            semester = student['semester']
            if semester not in students_by_semester:
                students_by_semester[semester] = []
            students_by_semester[semester].append(student)

        # enrolled Students by Semester
        for semester, students in students_by_semester.items():
            elements.append(Paragraph(f"Students Enrolled in {semester}", styles['Heading2']))
            elements.append(Spacer(1, 0.1 * inch))

            if students:
                students_table_data = [['ID', 'Name', 'Major', 'Department', 'Grade']]
                for student in students:
                    students_table_data.append([
                        str(student['student_id']),
                        student['student_name'],
                        student['major'],
                        student['department'],
                        student['grade']
                    ])

                students_table = Table(students_table_data,
                                       colWidths=[0.75 * inch, 2 * inch, 1.25 * inch, 1.5 * inch, 0.75 * inch])
                students_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('ALIGN', (1, 1), (1, -1), 'LEFT'),  # Align names to left
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                elements.append(students_table)
            else:
                elements.append(Paragraph("No students enrolled for this semester", styles['Normal']))

            elements.append(Spacer(1, 0.25 * inch))

        graded_students = [s for s in enrolled_students if s['grade'] != "Not Graded"]
        if graded_students:
            elements.append(Paragraph("Grade Distribution", styles['Heading2']))
            elements.append(Spacer(1, 0.1 * inch))

            grade_counts = {}
            for student in graded_students:
                grade = student['grade']
                if grade in grade_counts:
                    grade_counts[grade] += 1
                else:
                    grade_counts[grade] = 1

            grade_order = ['A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D', 'D-', 'F']
            sorted_grades = sorted(grade_counts.keys(), key=lambda g: grade_order.index(g) if g in grade_order else 999)

            stats_data = [['Grade', 'Count', 'Percentage']]
            for grade in sorted_grades:
                count = grade_counts[grade]
                percentage = (count / len(graded_students)) * 100
                stats_data.append([grade, str(count), f"{percentage:.1f}%"])

            stats_table = Table(stats_data, colWidths=[1 * inch, 1 * inch, 1.5 * inch])
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(stats_table)
            elements.append(Spacer(1, 0.25 * inch))

        doc.build(elements)

        pdf_data = buffer.getvalue()
        buffer.close()

        response = make_response(pdf_data)
        response.headers['Content-Disposition'] = f'attachment; filename=course_report_{course["course_id"]}.pdf'
        response.mimetype = 'application/pdf'

        return response
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        flash(f"Error generating report: {str(e)}", "danger")
        return redirect(url_for('courses.course_detail', id=id))
    finally:
        release_db_connection(conn)

@courses_bp.route('/add', methods=['GET', 'POST'])
def add_course():
    conn = get_db_connection()
    try:
        if request.method == 'POST':
            course_name = request.form['course_name']
            credits = request.form['credits']
            department_id = request.form['department_id']
            instructor_id = request.form.get('instructor_id', '')  # Optional
            semester = request.form.get('semester', '')  # Optional
            course_id = request.form.get('course_id', '').strip()  # Optional

            if not instructor_id:
                instructor_id = None

            cur = conn.cursor()

            # check if course id already exists before adding
            if course_id:
                cur.execute("SELECT COUNT(*) FROM courses WHERE course_id = %s", (course_id,))
                if cur.fetchone()[0] > 0:
                    cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
                    departments = cur.fetchall()

                    cur.execute("""
                        SELECT i.instructor_id, i.name, i.email, d.department_name 
                        FROM instructors i 
                        JOIN departments d ON i.department_id = d.department_id 
                        ORDER BY i.name
                    """)
                    instructors = cur.fetchall()
                    cur.close()
                    return render_template('add_course.html',
                                           message="Course ID already exists. Please use a different ID or leave blank for auto-generation.",
                                           message_type="danger",
                                           departments=departments,
                                           instructors=instructors)

                # insert a new course with provided information
                cur.execute("""
                    INSERT INTO courses (course_id, course_name, credits, department_id, instructor_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (course_id, course_name, credits, department_id, instructor_id))
            else:
                # find the next available course id
                cur.execute("""
                    SELECT MIN(t.course_id + 1) AS next_id 
                    FROM courses t 
                    WHERE NOT EXISTS (
                        SELECT 1 FROM courses t2 
                        WHERE t2.course_id = t.course_id + 1
                    )
                    UNION
                    SELECT 1
                    WHERE NOT EXISTS (SELECT 1 FROM courses WHERE course_id = 1)
                    ORDER BY next_id
                    LIMIT 1
                """)
                next_id = cur.fetchone()[0]

                if next_id is None:
                    next_id = 1

                # add semester offering for a course
                cur.execute("""
                    INSERT INTO courses (course_id, course_name, credits, department_id, instructor_id)
                    VALUES (%s, %s, %s, %s, %s)
                """, (next_id, course_name, credits, department_id, instructor_id))
                course_id = next_id

            if semester:
                try:
                    cur.execute("""
                        INSERT INTO enrollments (course_id, student_id, semester)
                        VALUES (%s, NULL, %s)
                    """, (course_id, semester))
                except Exception as e:
                    print(f"Warning: Could not add semester offering: {str(e)}")

            conn.commit()
            flash("Course added successfully!", "success")
            return redirect(url_for('courses.edit_course', id=course_id))

        cur = conn.cursor()

        # get all departments for dropdown selection
        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # get all instructors with their department info for dropdown
        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name 
            FROM instructors i 
            JOIN departments d ON i.department_id = d.department_id 
            ORDER BY i.name
        """)
        instructors = cur.fetchall()
        cur.close()
        return render_template('add_course.html', departments=departments, instructors=instructors)
    except Exception as e:
        conn.rollback()
        print(f"Error in add_course: {str(e)}")
        flash(f"Error adding course: {str(e)}", "danger")
        return redirect(url_for('courses.manage_courses'))
    finally:
        release_db_connection(conn)


@courses_bp.route('/edit')
def edit_courses():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')
        department_filter = request.args.get('department', '')
        page = int(request.args.get('page', 1))
        per_page = 30

        cur = conn.cursor()

        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        # search and filter courses with pagination
        query = """
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE 1=1
        """
        params = []

        if search_query:
            query += " AND (c.course_id::text ILIKE %s OR c.course_name ILIKE %s)"
            search_pattern = f"%{search_query}%"
            params.extend([search_pattern, search_pattern])

        if department_filter:
            query += " AND c.department_id = %s"
            params.append(department_filter)

        query += " ORDER BY c.course_id"

        # count total results for pagination
        count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        total_pages = (total_count + per_page - 1) // per_page
        offset = (page - 1) * per_page

        # limit results to specific page size and skip previous pages
        query += " LIMIT %s OFFSET %s"
        params.extend([per_page, offset])

        cur.execute(query, params)
        courses = cur.fetchall()

        cur.close()
        return render_template(
            'edit_courses.html',
            courses=courses,
            departments=departments,
            search_query=search_query,
            department_filter=department_filter,
            page=page,
            total_pages=total_pages,
            total_count=total_count
        )
    finally:
        release_db_connection(conn)


@courses_bp.route('/edit/<int:id>', methods=['GET'])
def edit_course(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # get course details with joins to related tables
        cur.execute("""
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE c.course_id = %s
        """, (id,))
        course = cur.fetchone()

        if course is None:
            flash("Course not found", "danger")
            return redirect(url_for('courses.edit_courses'))

        # count enrolled students for this course
        cur.execute("""
            SELECT COUNT(*) FROM enrollments 
            WHERE course_id = %s AND student_id IS NOT NULL
        """, (id,))
        enrolled_count = cur.fetchone()[0]

        # get semesters this course is offered in
        cur.execute("""
            SELECT DISTINCT semester FROM enrollments WHERE course_id = %s
        """, (id,))
        offered_semesters = [row[0] for row in cur.fetchall()]

        current_semester = None
        if offered_semesters:
            semester_order = {
                'Fall 2025': 1,
                'Spring 2025': 2,
                'Winter 2025': 3,
                'Fall 2024': 4,
                'Spring 2024': 5,
                'Winter 2024': 6,
                'Fall 2023': 7
            }
            current_semester = min(offered_semesters, key=lambda s: semester_order.get(s, 999))

        # get all students enrolled in this course with details
        cur.execute("""
            SELECT e.enrollment_id, s.student_id, s.name AS student_name, e.semester, e.grade
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            WHERE e.course_id = %s
            ORDER BY e.semester, s.name
        """, (id,))

        enrolled_students = []
        for row in cur.fetchall():
            enrolled_students.append({
                'enrollment_id': row[0],
                'student_id': row[1],
                'student_name': row[2],
                'semester': row[3],
                'grade': row[4]
            })

        cur.execute("SELECT department_id, department_name FROM departments ORDER BY department_name")
        departments = cur.fetchall()

        cur.execute("""
            SELECT i.instructor_id, i.name, i.email, d.department_name 
            FROM instructors i 
            JOIN departments d ON i.department_id = d.department_id 
            ORDER BY i.name
        """)
        instructors = cur.fetchall()

        semesters = ['Fall 2023', 'Winter 2024', 'Spring 2024', 'Fall 2024', 'Winter 2025', 'Spring 2025', 'Fall 2025', 'Winter 2026', 'Spring 2026', 'Fall 2026', 'Winter 2027', 'Spring 2027', 'Fall 2027']

        cur.close()
        return render_template(
            'edit_course.html',
            course=course,
            enrolled_count=enrolled_count,
            enrolled_students=enrolled_students,
            current_semester=current_semester,
            offered_semesters=offered_semesters,
            departments=departments,
            instructors=instructors,
            semesters=semesters
        )
    finally:
        release_db_connection(conn)


@courses_bp.route('/update/<int:id>', methods=['POST'])
def update_course(id):
    conn = get_db_connection()
    try:
        course_name = request.form['course_name']
        credits = request.form['credits']
        department_id = request.form['department_id']
        instructor_id = request.form.get('instructor_id', '')

        if not instructor_id:
            instructor_id = None

        cur = conn.cursor()

        # update course information
        cur.execute("""
            UPDATE courses
            SET course_name = %s, credits = %s, department_id = %s, instructor_id = %s
            WHERE course_id = %s
        """, (course_name, credits, department_id, instructor_id, id))

        selected_semesters = request.form.getlist('semesters[]')

        # get all semester offerings where student_id is NULL
        cur.execute("""
            SELECT DISTINCT semester FROM enrollments 
            WHERE course_id = %s AND student_id IS NULL
        """, (id,))
        current_semesters = [row[0] for row in cur.fetchall()]

        for semester in selected_semesters:
            if semester not in current_semesters:
                try:
                    # add a new semester offering
                    cur.execute("""
                        INSERT INTO enrollments (course_id, student_id, semester)
                        VALUES (%s, NULL, %s)
                    """, (id, semester))
                except Exception as e:
                    print(f"Warning: Could not add semester offering: {str(e)}")

        for semester in current_semesters:
            if semester not in selected_semesters:
                try:
                    # remove a semester offering
                    cur.execute("""
                        DELETE FROM enrollments 
                        WHERE course_id = %s AND semester = %s AND student_id IS NULL
                    """, (id, semester))
                except Exception as e:
                    print(f"Warning: Could not remove semester offering: {str(e)}")

        conn.commit()
        flash("Course updated successfully", "success")
        return redirect(url_for('courses.edit_course', id=id))
    except Exception as e:
        conn.rollback()
        flash(f"Error updating course: {str(e)}", "danger")
        return redirect(url_for('courses.edit_course', id=id))
    finally:
        release_db_connection(conn)

@courses_bp.route('/<int:id>')
def course_detail(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()

        # get basic course information
        cur.execute("""
            SELECT c.course_id, c.course_name, c.credits, c.department_id, c.instructor_id,
                   d.department_name, i.name AS instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE c.course_id = %s
        """, (id,))
        course_data = cur.fetchone()
        if course_data is None:
            flash("Course not found", "danger")
            return redirect(url_for('courses.course_offerings'))

        course = {
            'course_id':     course_data[0],
            'course_name':   course_data[1],
            'credits':       course_data[2],
            'department_id': course_data[3],
            'instructor_id': course_data[4],
            'department_name': course_data[5],
            'instructor_name': course_data[6]
        }

        # get all semesters for this course
        cur.execute("""
            SELECT DISTINCT semester
            FROM enrollments
            WHERE course_id = %s
            ORDER BY semester
        """, (id,))
        course['semesters'] = [row[0] for row in cur.fetchall()]

        # get all enrolled students with details
        cur.execute("""
            SELECT e.enrollment_id, s.student_id, s.name AS student_name,
                   d.department_name, s.major, e.semester, e.grade
            FROM enrollments e
            JOIN students s ON e.student_id = s.student_id
            LEFT JOIN departments d ON s.department_id = d.department_id
            WHERE e.course_id = %s
            ORDER BY e.semester, s.name
        """, (id,))

        students_by_semester = {}
        for enrollment_id, student_id, student_name, dept_name, major, semester, grade in cur.fetchall():
            students_by_semester.setdefault(semester, []).append({
                'enrollment_id': enrollment_id,
                'student_id':    student_id,
                'student_name':  student_name,
                'department_name': dept_name,
                'major':         major,
                'grade':         grade
            })

        # count total enrolled students
        cur.execute("""
            SELECT COUNT(*)
            FROM enrollments
            WHERE course_id = %s
              AND student_id IS NOT NULL
        """, (id,))
        total_students = cur.fetchone()[0]

        semester_order = [
            'Fall 2025', 'Spring 2025', 'Winter 2025',
            'Fall 2024', 'Spring 2024', 'Winter 2024',
            'Fall 2023', 'Winter 2026', 'Spring 2026',
            'Fall 2026', 'Winter 2027', 'Spring 2027',
            'Fall 2027'
        ]

        cur.close()

        return render_template(
            'course_detail.html',
            course=course,
            students_by_semester=students_by_semester,
            semester_order=semester_order,
            total_students=total_students
        )

    except Exception as e:
        print(f"Error in course_detail: {e}")
        flash(f"Error retrieving course details: {e}", "danger")
        return redirect(url_for('courses.course_offerings'))

    finally:
        release_db_connection(conn)



@courses_bp.route('/delete/<int:id>', methods=['POST'])
def delete_course(id):
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        # delete enrollments for a course
        cur.execute("DELETE FROM enrollments WHERE course_id = %s", (id,))
        # delete the course
        cur.execute("DELETE FROM courses WHERE course_id = %s", (id,))

        conn.commit()
        flash("Course deleted successfully", "success")
        return redirect(url_for('courses.edit_courses'))
    except Exception as e:
        conn.rollback()
        flash(f"Error deleting course: {str(e)}", "danger")
        return redirect(url_for('courses.edit_course', id=id))
    finally:
        release_db_connection(conn)

@courses_bp.route('/offerings')
def course_offerings():
    conn = get_db_connection()
    try:
        search_query = request.args.get('search', '')

        cur = conn.cursor()

        # get courses organized by department and semester
        query_base = """
            SELECT c.course_id, c.course_name, c.credits, d.department_name, 
                   i.name as instructor_name
            FROM courses c
            LEFT JOIN departments d ON c.department_id = d.department_id
            LEFT JOIN instructors i ON c.instructor_id = i.instructor_id
            WHERE 1=1
        """

        params = []
        if search_query:
            query_base += " AND (c.course_id::text = %s OR c.course_name ILIKE %s)"
            params.extend([search_query, f"%{search_query}%"])

        query_base += " ORDER BY d.department_name, c.course_name"

        cur.execute(query_base, params)
        all_courses = cur.fetchall()
        courses_by_semester = {}

        for course in all_courses:
            course_id = course[0]
            # get all semester offerings for a course
            cur.execute("""
                SELECT DISTINCT semester FROM enrollments 
                WHERE course_id = %s
                ORDER BY semester
            """, (course_id,))

            # Get all semesters for this course
            semesters = [row[0] for row in cur.fetchall()]

            # count enrolled students for a course in a specific semester
            for semester in semesters:
                cur.execute("""
                    SELECT COUNT(*) FROM enrollments
                    WHERE course_id = %s AND semester = %s AND student_id IS NOT NULL
                """, (course_id, semester))
                enrolled_count = cur.fetchone()[0]

                course_entry = {
                    'course_id': course[0],
                    'course_name': course[1],
                    'credits': course[2],
                    'instructor_name': course[4],
                    'enrolled_count': enrolled_count
                }

                if semester not in courses_by_semester:
                    courses_by_semester[semester] = {}

                department = course[3]
                if department not in courses_by_semester[semester]:
                    courses_by_semester[semester][department] = []

                courses_by_semester[semester][department].append(course_entry)

        semester_order = [
            'Fall 2027', 'Spring 2027', 'Winter 2027',
            'Fall 2026', 'Spring 2026', 'Winter 2026',
            'Fall 2025', 'Spring 2025', 'Winter 2025',
            'Fall 2024', 'Spring 2024', 'Winter 2024',
            'Fall 2023'
        ]

        cur.close()
        return render_template(
            'course_offerings.html',
            courses_by_semester=courses_by_semester,
            semester_order=semester_order,
            search_query=search_query
        )
    finally:
        release_db_connection(conn)