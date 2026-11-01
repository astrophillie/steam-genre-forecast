-- Observed activity attributed to each selected label in the eligible cohort.
-- One row per category/app/month; categories intentionally overlap.
SELECT gg.genre AS category, p.app_id, g.name, p.month, p.avg_players
FROM monthly_players AS p
JOIN games AS g ON g.app_id = p.app_id AND g.eligible = 1
JOIN game_genres AS gg ON gg.app_id = p.app_id
JOIN analysis_categories AS a ON a.genre = gg.genre
ORDER BY gg.genre, p.month, p.app_id;
