import httpx

BASE_URL = "http://localhost:8000/api/v1"
API_KEY = "replace-with-real-key"

headers = {"X-API-Key": API_KEY}


def main():
    with open("sample_resume.pdf", "rb") as f:
        files = {"file": ("sample_resume.pdf", f, "application/pdf")}
        r = httpx.post(f"{BASE_URL}/parse", files=files, headers=headers, timeout=120)
        print("parse", r.status_code, r.json())

    candidate_id = r.json().get("parsed_resume", {}).get("candidate_id")

    payload = {
        "candidate_id": candidate_id,
        "job_description": "We need a Python backend engineer with FastAPI, PostgreSQL, Docker and Kubernetes.",
        "required_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
        "nice_to_have_skills": ["Kubernetes", "AWS"],
        "min_years_experience": 3,
    }
    m = httpx.post(f"{BASE_URL}/match", json=payload, headers=headers, timeout=120)
    print("match", m.status_code, m.json())


if __name__ == "__main__":
    main()
