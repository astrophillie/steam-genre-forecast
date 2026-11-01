-- Latest-month impact of the recorded inclusion policy.
SELECT g.review_group, g.eligible, COUNT(*) AS observed_apps,
       SUM(p.avg_players) AS avg_players,
       100.0 * SUM(p.avg_players) /
           (SELECT SUM(avg_players) FROM monthly_players
            WHERE month = (SELECT MAX(month) FROM monthly_players)) AS activity_share_pct
FROM monthly_players AS p
JOIN games AS g ON g.app_id = p.app_id
WHERE p.month = (SELECT MAX(month) FROM monthly_players)
GROUP BY g.review_group, g.eligible
ORDER BY g.eligible DESC, avg_players DESC;
