using System.Collections;
using UnityEngine;
using UnityEngine.Events;
using BirdCombat.Birds;
using BirdCombat.Match;

namespace BirdCombat.Interactables
{
    public class NestController : MonoBehaviour
    {
        [SerializeField] private int startingEggs = 5;
        [SerializeField] private float stealDuration = 2.5f;
        [SerializeField] private Transform stealPoint;

        public UnityEvent<int> OnEggsChanged;

        private MatchManager matchManager;
        private TeamState owningTeam;
        private int eggCount;
        private bool isInitialized;

        public TeamState OwningTeam => owningTeam;
        public int EggCount => eggCount;

        public void Initialize(MatchManager manager, TeamState team)
        {
            matchManager = manager;
            owningTeam = team;
            eggCount = startingEggs;
            isInitialized = true;
            OnEggsChanged?.Invoke(eggCount);
        }

        public bool CanSteal => isInitialized && eggCount > 0;

        public void BeginSteal(BirdController thief)
        {
            if (!CanSteal || thief == null)
                return;

            StartCoroutine(StealRoutine(thief));
        }

        private IEnumerator StealRoutine(BirdController thief)
        {
            float elapsed = 0f;
            Vector3 startPos = thief.transform.position;

            while (elapsed < stealDuration)
            {
                if (!thief.IsAlive)
                    yield break;

                elapsed += Time.deltaTime;
                yield return null;
            }

            if (!CanSteal)
                yield break;

            eggCount--;
            OnEggsChanged?.Invoke(eggCount);
            thief.PickUpEgg(this);
            matchManager?.ReportEggStolen(thief, owningTeam);
        }

        public void NotifyEggCaptured(BirdController scorer, NestController originNest)
        {
            matchManager?.ReportEggCaptured(scorer, originNest?.OwningTeam, owningTeam);
        }

        public void ReturnEgg()
        {
            eggCount = Mathf.Min(startingEggs, eggCount + 1);
            OnEggsChanged?.Invoke(eggCount);
        }
    }
}
