CREATE OR REPLACE FUNCTION save_game_results(
    p_guild_id BIGINT,
    p_player_id BIGINT,
    p_score INT
)
RETURNS void
AS $$
BEGIN
    INSERT INTO games_scores (
        guild_id,
        player_id,
        score,
        played_at
    )
    VALUES (
        p_guild_id,
        p_player_id,
        p_score,
        NOW()
    )
    ON CONFLICT (guild_id, player_id)
    DO UPDATE
    SET
        score = games_scores.score + EXCLUDED.score,
        played_at = NOW();
END;
$$ LANGUAGE plpgsql;

ALTER TABLE games_scores
ADD CONSTRAINT unique_guild_player
UNIQUE (guild_id, player_id);
