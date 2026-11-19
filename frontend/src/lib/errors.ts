import { ApiError } from '../api/client'

/** Lines to show for a failed request: field messages for validation errors,
 *  the message plus any reason for others. */
export function errorMessages(error: unknown): string[] {
  if (error instanceof ApiError) {
    if (error.code === 'validation_error') {
      const fields = error.fieldMessages()
      return fields.length ? fields : [error.message]
    }
    const reason = typeof error.details.reason === 'string' ? error.details.reason : null
    return reason ? [error.message, reason] : [error.message]
  }
  return ['Something went wrong. Please try again.']
}
