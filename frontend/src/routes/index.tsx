import { createFileRoute } from '@tanstack/react-router'

import TripPlannerApp from '#/App'
import { Toaster } from '#/components/ui/sonner'

export const Route = createFileRoute('/')({
  component: TripPlannerRoute,
})

function TripPlannerRoute() {
  return (
    <>
      <TripPlannerApp />
      <Toaster />
    </>
  )
}
