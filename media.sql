ALTER TABLE public.game_scores
ADD CONSTRAINT game_scores_unique UNIQUE (guild_id, user_id, game_type);
