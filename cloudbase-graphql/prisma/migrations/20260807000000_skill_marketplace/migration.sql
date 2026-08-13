-- AlterTable: agent_skills aggregates
ALTER TABLE "agent_skills"
  ADD COLUMN "rating" DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN "rating_count" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "install_count" INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN "searchable_text" TEXT,
  ADD COLUMN "published_at" TIMESTAMP(3);

CREATE INDEX "agent_skills_rating_idx" ON "agent_skills"("rating");
CREATE INDEX "agent_skills_install_count_idx" ON "agent_skills"("install_count");
CREATE INDEX "agent_skills_is_public_rating_idx" ON "agent_skills"("public", "rating");
CREATE INDEX "agent_skills_is_public_install_count_idx" ON "agent_skills"("public", "install_count");
CREATE INDEX "agent_skills_is_public_category_idx" ON "agent_skills"("public", "category");

-- CreateTable: skill_ratings
CREATE TABLE "skill_ratings" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "score" INTEGER NOT NULL,
    "comment" TEXT,
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "skill_ratings_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "skill_ratings_user_id_skill_id_key" ON "skill_ratings"("user_id", "skill_id");
CREATE INDEX "skill_ratings_skill_id_idx" ON "skill_ratings"("skill_id");
CREATE INDEX "skill_ratings_skill_id_score_idx" ON "skill_ratings"("skill_id", "score");

ALTER TABLE "skill_ratings" ADD CONSTRAINT "skill_ratings_skill_id_fkey" FOREIGN KEY ("skill_id") REFERENCES "agent_skills"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- CreateTable: skill_installs
CREATE TABLE "skill_installs" (
    "id" TEXT NOT NULL,
    "user_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "agent_id" TEXT,
    "status" TEXT NOT NULL DEFAULT 'installed',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "skill_installs_pkey" PRIMARY KEY ("id")
);

CREATE UNIQUE INDEX "skill_installs_user_id_skill_id_key" ON "skill_installs"("user_id", "skill_id");
CREATE INDEX "skill_installs_skill_id_idx" ON "skill_installs"("skill_id");
CREATE INDEX "skill_installs_user_id_idx" ON "skill_installs"("user_id");

-- CreateTable: skill_orders
CREATE TABLE "skill_orders" (
    "id" TEXT NOT NULL,
    "buyer_id" TEXT NOT NULL,
    "seller_id" TEXT NOT NULL,
    "skill_id" TEXT NOT NULL,
    "price_cents" INTEGER NOT NULL,
    "price_model" TEXT,
    "status" TEXT NOT NULL DEFAULT 'pending',
    "metadata" JSONB NOT NULL DEFAULT '{}',
    "created_at" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "skill_orders_pkey" PRIMARY KEY ("id")
);

CREATE INDEX "skill_orders_buyer_id_idx" ON "skill_orders"("buyer_id");
CREATE INDEX "skill_orders_seller_id_idx" ON "skill_orders"("seller_id");
CREATE INDEX "skill_orders_skill_id_idx" ON "skill_orders"("skill_id");
CREATE INDEX "skill_orders_status_idx" ON "skill_orders"("status");
