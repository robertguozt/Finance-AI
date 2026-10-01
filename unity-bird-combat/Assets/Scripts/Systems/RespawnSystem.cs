using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using BirdCombat.Birds;
using BirdCombat.Match;

namespace BirdCombat.Systems
{
    public class RespawnSystem : MonoBehaviour
    {
        [SerializeField] private MatchManager matchManager;
        [SerializeField] private float respawnDelay = 8f;

        private readonly Dictionary<BirdController, Coroutine> queue = new();

        public void QueueRespawn(BirdController bird)
        {
            if (bird == null || queue.ContainsKey(bird))
                return;

            queue[bird] = StartCoroutine(RespawnRoutine(bird));
        }

        private IEnumerator RespawnRoutine(BirdController bird)
        {
            yield return new WaitForSeconds(respawnDelay);
            queue.Remove(bird);
            matchManager?.RespawnBird(bird);
        }
    }
}
