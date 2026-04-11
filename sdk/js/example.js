const BASE_URL = "http://localhost:8000/api/v1";
const API_KEY = "replace-with-real-key";

async function run() {
  const form = new FormData();
  const blob = new Blob(["Sample resume text with Python, FastAPI, Docker"], { type: "text/plain" });
  form.append("file", blob, "resume.txt");

  const parseRes = await fetch(`${BASE_URL}/parse`, {
    method: "POST",
    headers: { "X-API-Key": API_KEY },
    body: form,
  });
  const parseJson = await parseRes.json();
  console.log("parse", parseRes.status, parseJson);

  const candidateId = parseJson?.parsed_resume?.candidate_id;

  const matchRes = await fetch(`${BASE_URL}/match`, {
    method: "POST",
    headers: {
      "X-API-Key": API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      candidate_id: candidateId,
      job_description: "Looking for backend Python engineer with PostgreSQL and Docker.",
      required_skills: ["Python", "PostgreSQL", "Docker"],
      nice_to_have_skills: ["Kubernetes"],
      min_years_experience: 2,
    }),
  });
  const matchJson = await matchRes.json();
  console.log("match", matchRes.status, matchJson);
}

run().catch(console.error);
