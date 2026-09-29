from __future__ import annotations

import re
from typing import TypedDict


class ScheduleEntry(TypedDict):
    course_code: str
    course_name: str
    day: str
    start_time: str
    end_time: str
    room: str
    instructor: str


class TimetableValidationError(ValueError):
    pass


class StudentNotFoundError(LookupError):
    pass


STUDENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9/_-]{2,29}$")
COURSE_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{1,19}$")

DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
VALID_DAYS = set(DAY_ORDER)

MOCK_TIMETABLE: dict[str, list[ScheduleEntry]] = {
    "2300712345": [
        {
            "course_code": "BSE4104",
            "course_name": "Emerging Trends in Software Engineering",
            "day": "monday",
            "start_time": "09:00",
            "end_time": "11:00",
            "room": "CIT-LR1",
            "instructor": "Dr. K. Mugisha",
        },
        {
            "course_code": "BSE4104",
            "course_name": "Emerging Trends in Software Engineering",
            "day": "wednesday",
            "start_time": "09:00",
            "end_time": "11:00",
            "room": "CIT-LR1",
            "instructor": "Dr. K. Mugisha",
        },
        {
            "course_code": "CSC3103",
            "course_name": "Database Systems II",
            "day": "tuesday",
            "start_time": "14:00",
            "end_time": "16:00",
            "room": "CIT-201",
            "instructor": "Ms. A. Nabatanzi",
        },
        {
            "course_code": "CSC3105",
            "course_name": "Software Project Management",
            "day": "thursday",
            "start_time": "11:00",
            "end_time": "13:00",
            "room": "CIT-105",
            "instructor": "Mr. R. Ochieng",
        },
    ],
    "2300798765": [
        {
            "course_code": "BSE4104",
            "course_name": "Emerging Trends in Software Engineering",
            "day": "monday",
            "start_time": "09:00",
            "end_time": "11:00",
            "room": "CIT-LR1",
            "instructor": "Dr. K. Mugisha",
        },
        {
            "course_code": "MTH2201",
            "course_name": "Discrete Mathematics",
            "day": "friday",
            "start_time": "08:00",
            "end_time": "10:00",
            "room": "CIT-302",
            "instructor": "Dr. F. Tumusiime",
        },
    ],
}


def _validate_student_id(student_id: str) -> str:
    if not isinstance(student_id, str) or not STUDENT_ID_PATTERN.match(student_id):
        raise TimetableValidationError(f"Invalid student_id: {student_id!r}")
    return student_id


def _validate_course_code(course_code: str | None) -> str | None:
    if course_code is None:
        return None
    if not isinstance(course_code, str) or not COURSE_CODE_PATTERN.match(course_code):
        raise TimetableValidationError(f"Invalid course_code: {course_code!r}")
    return course_code


def _validate_day(day: str | None) -> str | None:
    if day is None:
        return None
    if not isinstance(day, str):
        raise TimetableValidationError(f"Invalid day: {day!r}")
    lowered = day.strip().lower()
    if lowered not in VALID_DAYS:
        raise TimetableValidationError(f"Invalid day: {day!r}")
    return lowered


def get_course_schedule(
    student_id: str,
    course_code: str | None = None,
    day: str | None = None,
) -> list[ScheduleEntry]:
    student_id = _validate_student_id(student_id)
    course_code = _validate_course_code(course_code)
    day = _validate_day(day)

    if student_id not in MOCK_TIMETABLE:
        raise StudentNotFoundError(f"No timetable found for student_id {student_id!r}")

    entries = MOCK_TIMETABLE[student_id]

    if course_code is not None:
        entries = [e for e in entries if e["course_code"].lower() == course_code.lower()]
    if day is not None:
        entries = [e for e in entries if e["day"] == day]

    day_index = {name: i for i, name in enumerate(DAY_ORDER)}
    return sorted(entries, key=lambda e: (day_index[e["day"]], e["start_time"]))
