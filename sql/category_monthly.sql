-- One row per selected category/month, using eligible apps only.
-- Expected apps are those whose own first-to-last recorded span covers the month.
-- Activity stays NULL if no apps were observed; zero observed activity remains zero.
WITH RECURSIVE calendar(month) AS (
    SELECT MIN(month) FROM monthly_players
    UNION ALL
    SELECT date(month, '+1 month') FROM calendar
    WHERE month < (SELECT MAX(month) FROM monthly_players)
),
expected AS (
    SELECT gg.genre AS category, c.month, COUNT(*) AS expected_apps
    FROM game_genres AS gg
    JOIN games AS g ON g.app_id = gg.app_id AND g.eligible = 1
    JOIN analysis_categories AS a ON a.genre = gg.genre
    JOIN app_coverage AS s ON s.app_id = g.app_id
    JOIN calendar AS c ON c.month BETWEEN s.first_month AND s.last_month
    GROUP BY gg.genre, c.month
),
observed AS (
    SELECT gg.genre AS category, p.month, COUNT(*) AS observed_apps,
           SUM(p.avg_players) AS avg_players
    FROM monthly_players AS p
    JOIN games AS g ON g.app_id = p.app_id AND g.eligible = 1
    JOIN game_genres AS gg ON gg.app_id = g.app_id
    JOIN analysis_categories AS a ON a.genre = gg.genre
    GROUP BY gg.genre, p.month
)
SELECT e.category, e.month, o.avg_players,
       COALESCE(o.observed_apps, 0) AS observed_apps, e.expected_apps,
       e.expected_apps - COALESCE(o.observed_apps, 0) AS internal_missing_apps,
       1.0 * COALESCE(o.observed_apps, 0) / e.expected_apps AS coverage_rate
FROM expected AS e
LEFT JOIN observed AS o ON o.category = e.category AND o.month = e.month
ORDER BY e.category, e.month;
