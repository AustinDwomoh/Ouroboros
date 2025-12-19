DROP FUNCTION get_leaderboard(p_guild_id BIGINT);
CREATE OR REPLACE FUNCTION get_leaderboard(p_guild_id BIGINT)
    RETURNS TABLE (
        user_id BIGINT,
        total_score INT
    ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                user_id, 
                SUM(score) AS total_score
            FROM 
                game_scores
            WHERE 
                guild_id = get_leaderboard.p_guild_id
            GROUP BY 
                user_id
            ORDER BY 
                total_score DESC;
        END;
    $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_game_leaderboard(p_guild_id BIGINT, p_game_type TEXT)
 RETURNS TABLE (
     user_id BIGINT,
     score INT
 ) AS $$
    BEGIN
        RETURN QUERY
        SELECT 
            user_id, 
            score
        FROM 
            game_scores
        WHERE 
            guild_id = get_game_leaderboard.p_guild_id
            AND game_type = get_game_leaderboard.p_game_type
        ORDER BY 
            score DESC;
    END;
$$ LANGUAGE plpgsql;    


CREATE OR REPLACE FUNCTION get_player_scores(p_user_id BIGINT,p_guild_id BIGINT)
    RETURNS TABLE (
        score INT,
        game_type TEXT
    ) AS $$
        BEGIN
            RETURN QUERY
            SELECT 
                score,
                game_type
            FROM 
                game_scores
            WHERE 
                guild_id = get_player_scores.p_guild_id AND user_id = get_player_scores.p_user_id
            ORDER BY 
                score DESC;
        END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION get_player_game_scores(p_guild_id BIGINT, p_game_type TEXT,p_user_id BIGINT)
    RETURNS TABLE (
        score INT,
        game_type TEXT
    ) AS $$
        BEGIN
            RETURN QUERY
            SELECT  
                score,
                game_type
            FROM 
                game_scores
            WHERE 
                guild_id = get_player_game_scores.p_guild_id
                AND game_type = get_player_game_scores.p_game_type
                AND user_id = get_player_game_scores.p_user_id
            ORDER BY 
                score DESC;
        END;
$$ LANGUAGE plpgsql;