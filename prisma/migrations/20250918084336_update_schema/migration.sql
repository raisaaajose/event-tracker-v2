/*
  Warnings:

  - You are about to drop the column `lastEmailFetch` on the `CalendarSync` table. All the data in the column will be lost.

*/
-- AlterTable
ALTER TABLE "CalendarSync" DROP COLUMN "lastEmailFetch",
ADD COLUMN     "lastProcessedDate" TIMESTAMP(3);

-- AlterTable
ALTER TABLE "Event" ADD COLUMN     "sourceId" TEXT;

-- CreateIndex
CREATE INDEX "Event_sourceId_idx" ON "Event"("sourceId");
