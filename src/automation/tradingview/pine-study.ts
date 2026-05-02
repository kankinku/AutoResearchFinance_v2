const declarationExpression =
  /\b(strategy|indicator)\s*\(\s*(['"`])([^'"`]+)\2/;

export function extractStudyTitle(source: string): string | null {
  const match = source.match(declarationExpression);
  return match?.[3] ?? null;
}

export function ensureCandidateStudyTitle(
  source: string,
  candidateId: string,
): { source: string; studyTitle: string | null } {
  const originalTitle = extractStudyTitle(source);
  if (!originalTitle) {
    return {
      source,
      studyTitle: null,
    };
  }

  const studyTitle = `${originalTitle} [${candidateId}]`;
  return {
    source: source.replace(declarationExpression, (_match, kind: string, quote: string) => {
      return `${kind}(${quote}${studyTitle}${quote}`;
    }),
    studyTitle,
  };
}
