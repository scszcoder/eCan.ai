-- CreateTable: agent_chat_messages
CREATE TABLE "agent_chat_messages" (
    "id" TEXT NOT NULL,
    "owner" TEXT NOT NULL,
    "session_id" TEXT NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "goals" TEXT,
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "agent_chat_messages_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "agent_chat_messages_owner_session_id_created_at_idx" ON "agent_chat_messages"("owner", "session_id", "created_at");
