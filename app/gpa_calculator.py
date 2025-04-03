
def calculate_gpa(courses):
    gpa_points = 0
    completed_credits = 0

    # Process each course
    for course in courses:
        # Only consider courses with grades
        if course[3] is not None:
            credits = course[1] or 0  # Default to 0 if credits is None
            grade = course[3]

            # Convert letter grade to GPA points
            grade_value = 0
            if grade == 'A+':
                grade_value = 4.0
            elif grade == 'A':
                grade_value = 4.0
            elif grade == 'A-':
                grade_value = 3.7
            elif grade == 'B+':
                grade_value = 3.3
            elif grade == 'B':
                grade_value = 3.0
            elif grade == 'B-':
                grade_value = 2.7
            elif grade == 'C+':
                grade_value = 2.3
            elif grade == 'C':
                grade_value = 2.0
            elif grade == 'C-':
                grade_value = 1.7
            elif grade == 'D+':
                grade_value = 1.3
            elif grade == 'D':
                grade_value = 1.0
            elif grade == 'D-':
                grade_value = 0.7
            elif grade == 'F':
                grade_value = 0.0

            # Accumulate weighted grade points and credits
            gpa_points += grade_value * credits
            completed_credits += credits

    # Calculate GPA
    if completed_credits > 0:
        gpa = gpa_points / completed_credits
        return (gpa, completed_credits, gpa_points)
    else:
        return (None, 0, 0)
