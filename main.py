#!/usr/bin/env python3

import os
import re
from datetime import datetime
from typing import List

import requests
from pydantic import BaseModel

from rich.console import Console
from rich.table import Table

# Define Pydantic models for structured validation and parsing
class Book(BaseModel):
    uuid: str
    label: str


class User(BaseModel):
    name: str
    uuid: str


class Note(BaseModel):
    uuid: str
    created_at: str
    updated_at: str
    content: str
    added_on: int
    public: bool
    usn: int
    book: Book
    user: User


class NotesResponse(BaseModel):
    notes: List[Note]
    total: int


def get_auth_key() -> str:
    """
    Logs into the Dnote API using credentials from environment variables
    and returns an authentication key.

    :return: Authentication key if successful, otherwise ""
    """
    email = os.getenv("DNOTE_EMAIL")
    password = os.getenv("DNOTE_PASSWORD")

    if not email or not password:
        print("Error: DNOTE_EMAIL or DNOTE_PASSWORD environment variable not set.")
        return ""

    url = "https://app.getdnote.com/api/v3/signin"

    payload = {"email": email, "password": password}

    headers = {
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(url, json=payload, headers=headers, verify=True)
        response.raise_for_status()  # Raise exception for HTTP errors
        return response.json().get("key")  # Extract authentication key
    except requests.exceptions.RequestException as e:
        print(f"Login failed: {e}")
        return ""


def fetch_notes(auth_key: str) -> NotesResponse:
    """
    Fetch notes from the Dnote API and return a NotesResponse object.

    :return: NotesResponse object containing all notes and total count
    """

    if not auth_key:
        return NotesResponse(notes=[], total=0)

    url = "https://app.getdnote.com/api/v3/notes"
    headers = {
        "Authorization": f"Bearer {auth_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return NotesResponse.model_validate(response.json())

    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch notes: {e}")
        return NotesResponse(notes=[], total=0)


def extract_due_date(note: Note) -> datetime:
    """
    Extracts the due date from the note content.

    - If the note starts with "(WAITING)", finds the first valid date in the content.
    - Otherwise, assumes the date is in the first 9 characters ("dd mmm YY").
    - If no valid date is found, returns datetime.max.

    :param note: The Note object
    :return: A datetime object representing the due date
    """
    # Regex pattern for a date in format "dd mmm YY"
    date_pattern = r"\b\d{2} [A-Za-z]{3} \d{2}\b"

    if note.content.startswith("(WAITING)"):
        # Find the first valid date anywhere in the text
        match = re.search(date_pattern, note.content)
        if match:
            return datetime.strptime(match.group(), "%d %b %y")

    else:
        # Assume the date is in the first 9 characters
        try:
            return datetime.strptime(note.content[:9], "%d %b %y")
        except ValueError:
            pass  # If parsing fails, fall through to return datetime.max

    return datetime.max  # Default to a far future date if no valid date is found

def clean_content(note: Note) -> str:
    """
    Cleans a note's content by:
    - Removing "(WAITING) >>> <date> >>>" if present
    - Removing "<date> >>>" if present at the beginning
    - Returning only the meaningful note text

    :param note: The Note object
    :return: A cleaned-up version of the note's content
    """

    # Regex pattern for a date in "dd mmm YY" format
    date_pattern = r"\b\d{2} [A-Za-z]{3} \d{2}\b"

    content = note.content.strip()  # Remove leading/trailing spaces

    if content.startswith("(WAITING)"):
        # Remove "(WAITING) >>>" and extract the real content after the date
        content = re.sub(r"^\(WAITING\) >>> " + date_pattern + r" >>> ", "", content)

    else:
        # Remove just the leading "<date> >>>" pattern
        content = re.sub(r"^" + date_pattern + r" >>> ", "", content)

    return content.strip()  # Final cleanup

def print_section(title, notes, note_width):
    if notes:
        console.print(f"\n{title}")

        notes_sorted = sorted(notes, key=extract_due_date )

        table = Table(show_header=False, border_style="grey50")
        table.add_column("Due Date", style="red", min_width=12, justify="center")
        table.add_column("Content", style="yellow", min_width=note_width, max_width=note_width, overflow="fold")
        table.add_column("Book", style="white", min_width=15, justify="center")

        today = datetime.today()  # Get today's date

        for note in notes_sorted:
            due_date = extract_due_date(note)
            due_date_str = due_date.strftime("%d %b %y")

            # Apply red color if the due date is in the past
            date_color = "[red]" if due_date < today else "[white]"
            formatted_due_date = f"{date_color}{due_date_str}[/]"

            table.add_row(
                formatted_due_date,
                clean_content(note),
                note.book.label.title()
            )

        console.print(table)

if __name__ == "__main__":
    notes_response = fetch_notes(get_auth_key())

    if notes_response.total == 0:
        print("⚠️ No notes found. This could be due to:")
        print("   - A problem with the API request")
        print("   - An incorrect or expired authentication key")
        print("   - No notes being available from Dnote account")
        print("\n🔍 Please check your API key and try again.")
    else:
        # Organize notes
        today = datetime.today()
        urgent = []
        upcoming = []
        long_term = []
        waiting = []
        max_width = 50
        for note in notes_response.notes:
            cleaned_content = clean_content(note)
            if len(cleaned_content) > 50:
                max_width = len(cleaned_content)

            if note.content.startswith("(WAITING)"):
                waiting.append(note)
                continue  # Skip further categorization

            due_date = extract_due_date(note)
            days_until_due = (due_date - today).days

            if days_until_due < 7:
                urgent.append(note)
            elif 7 <= days_until_due < 14:
                upcoming.append(note)
            else:
                long_term.append(note)

        console = Console()

        print_section("Urgent:", urgent, max_width)
        print_section("Upcoming", upcoming, max_width)
        print_section("Longer Term", long_term, max_width)
        print_section("Waiting on Input from Others", waiting, max_width)