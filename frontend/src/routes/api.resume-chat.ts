import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/api/resume-chat')({
  server: {
    handlers: {
      POST: async () =>
        new Response(
          JSON.stringify({
            error: 'This TanStack Start app is configured for the trip planner.',
          }),
          {
            status: 404,
            headers: { 'Content-Type': 'application/json' },
          },
        ),
    },
  },
})
