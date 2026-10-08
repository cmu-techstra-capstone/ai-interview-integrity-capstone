export type ReviewStatus =
  "Awaiting review" | "In review" | "Reviewed" | "Follow-up needed";
export type Feedback = "Valid signal" | "False alarm" | "Inconclusive";
export type Modality = "audio" | "transcript" | "visual";
export interface EvidenceSignal {
  signal_name: string;
  modality: Modality;
  value: number | string | null;
  confidence: null;
  quality_status: "ok" | "warning" | "unusable" | "unknown";
  supporting_timestamps: [number, number][];
  supporting_transcript_span: {
    text: string;
    start: number | null;
    end: number | null;
  } | null;
  explanation: string;
  source_features: string[];
  sample_key: string;
}
export interface Answer {
  id: string;
  question: string;
  start: number;
  end: number;
  score: number | null;
  transcript: { text: string; start: number }[];
  signals: EvidenceSignal[];
  speechRate: number | null;
  latency: number | null;
  baselineRate: number | null;
  baselineLatency: number | null;
}
export interface Interview {
  id: string;
  candidate: string;
  role: string;
  team: string;
  interviewer: string;
  date: string;
  status: ReviewStatus;
  processing: "Ready" | "Processing" | "Failed";
  consent: boolean;
  quality: "Good" | "Limited audio" | "Missing transcript";
  answers: Answer[];
}
export interface Review {
  notes: string;
  feedback: Feedback | "";
  followup: boolean;
  reviewed: boolean;
}
export type Reviews = Record<string, Review>;
export const emptyReview: Review = {
  notes: "",
  feedback: "",
  followup: false,
  reviewed: false,
};
export const band = (score: number | null) =>
  score === null
    ? "Unscored"
    : score <= 2
      ? "Low signal"
      : score <= 5
        ? "Review"
        : "Strong signal";
export const tone = (score: number | null) =>
  score === null
    ? "neutral"
    : score <= 2
      ? "teal"
      : score <= 5
        ? "amber"
        : "coral";
export const fmtTime = (value: number) =>
  `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${Math.floor(value % 60)
    .toString()
    .padStart(2, "0")}`;
const questions = [
  "Tell me about a data pipeline you designed and the tradeoffs you made.",
  "How would you investigate a slow SQL query?",
  "How do you make an ingestion pipeline safe to rerun?",
  "Describe a time you handled an unexpected data quality issue.",
  "How would you explain an engineering tradeoff to a nontechnical stakeholder?",
];
const texts = [
  [
    "I worked on an ingestion pipeline that brought operational data into a lakehouse.",
    "We used incremental loads so we could keep the refresh time manageable.",
    "The main tradeoff was balancing freshness with the cost of frequent processing.",
  ],
  [
    "I would start with the execution plan and look at where the query spends its time.",
    "Then I would check whether the filters use an index and whether the joins increase the row count unexpectedly.",
    "I would compare a few changes against the same dataset before choosing a fix.",
  ],
  [
    "I would use a stable key and make the write operation idempotent.",
    "That could mean merging records rather than appending everything again.",
    "I would also track checkpoints, and test retries after a partial failure.",
  ],
  [
    "A refresh completed successfully, but one of the totals did not match the source.",
    "We traced it to duplicate records from an upstream retry.",
    "I added a uniqueness check and worked with the source team to prevent repeats.",
  ],
  [
    "I would explain the effect on the user first, then describe the available options.",
    "For example, more frequent refreshes give fresher data but increase processing cost.",
    "I would agree on the freshness requirement before choosing the implementation.",
  ],
];
export function makeAnswers(
  id: string,
  seed: number,
  quality: Interview["quality"],
): Answer[] {
  return questions.map((question, j) => {
    const start = j * 155 + 35,
      end = start + 110;
    const score =
      quality === "Missing transcript" && j % 2 === 0
        ? null
        : [1, 4, 7, 2, 5][(j + seed) % 5];
    const rate = quality !== "Good" ? null : 132 + ((seed * 13 + j * 17) % 58);
    const latency = 2 + ((seed + j * 3) % 9) / 2;
    const key = `${id}/Q0${j + 1}`;
    const transcript =
      quality === "Missing transcript"
        ? []
        : texts[j].map((text, k) => ({ text, start: start + k * 30 }));
    const signal = (
      signal_name: string,
      modality: Modality,
      value: number | string | null,
      explanation: string,
    ): EvidenceSignal => ({
      signal_name,
      modality,
      value,
      confidence: null,
      quality_status:
        modality === "audio" && quality === "Limited audio"
          ? "unusable"
          : value === null
            ? "unknown"
            : "ok",
      supporting_timestamps: [[start, end]],
      supporting_transcript_span:
        modality === "transcript" && transcript.length
          ? {
              text: transcript.map((t) => t.text).join(" "),
              start: null,
              end: null,
            }
          : null,
      explanation,
      source_features: [signal_name],
      sample_key: key,
    });
    return {
      id: `Q0${j + 1}`,
      question,
      start,
      end,
      score,
      transcript,
      speechRate: rate,
      latency,
      baselineRate: quality === "Good" ? 145 : null,
      baselineLatency: quality === "Good" ? 3 : null,
      signals: [
        signal(
          "long_pause_count",
          "audio",
          quality === "Limited audio" ? null : 2 + j,
          quality === "Limited audio"
            ? "Long pauses are not measurable because audio is unusable."
            : `Pauses of at least one second: ${2 + j}. This observation covers the answer window.`,
        ),
        signal(
          "speech_rate",
          "audio",
          rate,
          rate === null
            ? "Speech rate is not measurable."
            : `Speech rate: ${rate} words per minute across this answer.`,
        ),
        signal(
          "word_count",
          "transcript",
          transcript.length
            ? transcript
                .map((t) => t.text.split(" ").length)
                .reduce((a, b) => a + b, 0)
            : null,
          transcript.length
            ? "Word count measured from the supplied transcript."
            : "No transcript was supplied; word count is not measurable.",
        ),
      ],
    };
  });
}
const people = [
  "Alex Morgan",
  "Jordan Lee",
  "Taylor Brooks",
  "Sam Rivera",
  "Casey Patel",
  "Jamie Chen",
  "Drew Wilson",
  "Riley Park",
  "Avery Thomas",
  "Quinn Davis",
  "Cameron Reed",
  "Robin Shah",
];
export function createDemoInterviews(): Interview[] {
  return Array.from({ length: 36 }, (_, i) => {
    const id = `INT-${1048 - i}`;
    const quality: Interview["quality"] =
      i % 9 === 4
        ? "Limited audio"
        : i % 11 === 6
          ? "Missing transcript"
          : "Good";
    return {
      id,
      candidate: people[i % people.length],
      role: ["Data Engineer", "Java Developer", "BI Analyst", "ML Engineer"][
        i % 4
      ],
      team: [
        "Data & Analytics",
        "Engineering",
        "Data & Analytics",
        "AI Solutions",
      ][i % 4],
      interviewer: ["Priya Nair", "Michael Evans", "Paul Bennett"][i % 3],
      date: new Date(Date.UTC(2026, 9, 8 - i * 2)).toISOString().slice(0, 10),
      status: (
        [
          "Awaiting review",
          "In review",
          "Reviewed",
          "Follow-up needed",
          "Reviewed",
          "Reviewed",
        ] as ReviewStatus[]
      )[i % 6],
      processing: i === 9 ? "Failed" : i === 3 ? "Processing" : "Ready",
      consent: true,
      quality,
      answers: makeAnswers(id, i, quality),
    };
  });
}
export const reviewKey = (id: string, q: string) => `${id}/${q}`;
export function statusOf(i: Interview, reviews: Reviews): ReviewStatus {
  const records = i.answers.map((a) => reviews[reviewKey(i.id, a.id)]);
  if (records.some((r) => r?.followup)) return "Follow-up needed";
  if (records.every((r) => r?.reviewed)) return "Reviewed";
  if (records.some((r) => r?.reviewed)) return "In review";
  return i.status;
}

export function createDemoReviews(interviews: Interview[]): Reviews {
  const reviews: Reviews = {};
  for (const interview of interviews) {
    interview.answers.forEach((answer, index) => {
      if (
        interview.status === "Reviewed" ||
        (interview.status === "In review" && index < 2) ||
        (interview.status === "Follow-up needed" && index === 0)
      ) {
        reviews[`${interview.id}/${answer.id}`] = {
          ...emptyReview,
          reviewed: true,
          followup: interview.status === "Follow-up needed",
        };
      }
    });
  }
  return reviews;
}
