export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
    /** Données renvoyées avec l'erreur (ex. nouveau montant de cash out). */
    public data?: Record<string, unknown>,
  ) {
    super(message);
  }
}
