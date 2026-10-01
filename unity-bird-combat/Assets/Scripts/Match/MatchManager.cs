using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Events;
using BirdCombat.Birds;
using BirdCombat.Interactables;
using BirdCombat.Systems;

namespace BirdCombat.Match
{
    public class MatchManager : MonoBehaviour
    {
        [SerializeField] private List<TeamState> teams = new();
        [SerializeField] private int eggsNeededToWin = 3;
        [SerializeField] private float roundDurationSeconds = 480f;
        [SerializeField] private float suddenDeathDurationSeconds = 120f;
        [SerializeField] private float countdownSeconds = 5f;
        [SerializeField] private RespawnSystem respawnSystem;

        public UnityEvent<TeamState, VictoryCondition> OnMatchEnded;
        public UnityEvent<MatchPhase> OnPhaseChanged;

        public MatchPhase Phase { get; private set; } = MatchPhase.Lobby;
        public IReadOnlyList<TeamState> Teams => teams;

        private readonly Dictionary<TeamState, int> spawnIndices = new();
        private Coroutine matchFlow;
        private TeamState winningTeam;

        private void Start()
        {
            InitializeTeams();
            matchFlow = StartCoroutine(MatchLoop());
        }

        private void InitializeTeams()
        {
            foreach (var team in teams)
            {
                if (team == null || !team.IsConfigured)
                    continue;

                spawnIndices[team] = 0;
                team.Nest.Initialize(this, team);
            }
        }

        private IEnumerator MatchLoop()
        {
            SetPhase(MatchPhase.Countdown);
            yield return new WaitForSeconds(countdownSeconds);

            SetPhase(MatchPhase.Active);
            float timer = roundDurationSeconds;

            while (Phase == MatchPhase.Active)
            {
                timer -= Time.deltaTime;
                if (timer <= 0f)
                {
                    TriggerSuddenDeath();
                }

                yield return null;
            }

            if (Phase == MatchPhase.SuddenDeath)
            {
                float suddenTimer = suddenDeathDurationSeconds;
                while (Phase == MatchPhase.SuddenDeath)
                {
                    suddenTimer -= Time.deltaTime;
                    if (suddenTimer <= 0f)
                    {
                        DeclareTimeoutWinner();
                    }

                    yield return null;
                }
            }
        }

        private void TriggerSuddenDeath()
        {
            SetPhase(MatchPhase.SuddenDeath);
        }

        private void DeclareTimeoutWinner()
        {
            if (Phase == MatchPhase.Completed)
                return;

            var best = teams.OrderByDescending(t => t.EggsCaptured).ThenByDescending(t => t.LivingBirds).FirstOrDefault();
            DeclareVictory(best, VictoryCondition.Timeout);
        }

        private void SetPhase(MatchPhase newPhase)
        {
            if (Phase == newPhase)
                return;

            Phase = newPhase;
            OnPhaseChanged?.Invoke(Phase);
        }

        public void ReportEggStolen(BirdController thief, TeamState defendingTeam)
        {
            // Hook for UI feedback and announcer logic
        }

        public void ReportEggCaptured(BirdController scorer, TeamState sourceTeam, TeamState scoringTeam)
        {
            if (Phase == MatchPhase.Completed || scoringTeam == null)
                return;

            scoringTeam.EggsCaptured++;

            if (scoringTeam.EggsCaptured >= eggsNeededToWin)
            {
                DeclareVictory(scoringTeam, VictoryCondition.EggCapture);
            }
        }

        public void ReportBirdDown(BirdController fallen, BirdController killer)
        {
            if (Phase == MatchPhase.Completed || fallen == null)
                return;

            var team = fallen.OwningTeam;
            if (team == null)
                return;

            if (Phase != MatchPhase.SuddenDeath)
            {
                respawnSystem?.QueueRespawn(fallen);
            }

            if (!team.HasLivingBirds)
            {
                var opposing = GetOpposingTeam(team);
                DeclareVictory(opposing, VictoryCondition.TeamWipe);
            }
        }

        public void RespawnBird(BirdController bird)
        {
            if (bird == null || Phase == MatchPhase.Completed)
                return;

            var team = bird.OwningTeam;
            if (team == null)
                return;

            var spawn = SelectSpawn(team);
            bird.Respawn(spawn);
        }

        private Transform SelectSpawn(TeamState team)
        {
            if (team.SpawnPoints == null || team.SpawnPoints.Length == 0)
            {
                return team.Nest != null ? team.Nest.transform : null;
            }

            int index = spawnIndices.TryGetValue(team, out var current) ? current : 0;
            var spawn = team.SpawnPoints[index % team.SpawnPoints.Length];
            spawnIndices[team] = (index + 1) % team.SpawnPoints.Length;
            return spawn;
        }

        private TeamState GetOpposingTeam(TeamState eliminated)
        {
            return teams.FirstOrDefault(t => t != null && t != eliminated);
        }

        private void DeclareVictory(TeamState team, VictoryCondition victory)
        {
            if (Phase == MatchPhase.Completed)
                return;

            winningTeam = team;
            SetPhase(MatchPhase.Completed);
            OnMatchEnded?.Invoke(team, victory);

            if (matchFlow != null)
            {
                StopCoroutine(matchFlow);
                matchFlow = null;
            }
        }
    }
}
