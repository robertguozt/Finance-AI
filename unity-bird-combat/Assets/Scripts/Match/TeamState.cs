using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using BirdCombat.Birds;
using BirdCombat.Interactables;

namespace BirdCombat.Match
{
    [System.Serializable]
    public class TeamState
    {
        [Tooltip("Internal identifier used to match birds to teams")]
        public string Id;

        [Tooltip("Readable name shown on the HUD")]
        public string DisplayName;

        public Color TeamColor = Color.white;

        [Tooltip("Spawn transforms that the respawn system can cycle through")] 
        public Transform[] SpawnPoints = System.Array.Empty<Transform>();

        [Tooltip("Nest that owns the team's eggs")] 
        public NestController Nest;

        [HideInInspector] public List<BirdController> ActiveBirds = new();
        [HideInInspector] public int EggsCaptured;

        public int LivingBirds => ActiveBirds.Count(b => b && b.IsAlive);
        public bool HasLivingBirds => LivingBirds > 0;
        public bool IsConfigured => Nest != null && !string.IsNullOrEmpty(Id);
    }
}
