using UnityEngine;

namespace BirdCombat.Birds
{
    [CreateAssetMenu(fileName = "BirdClass", menuName = "Bird Combat/Bird Class", order = 0)]
    public class BirdClassDefinition : ScriptableObject
    {
        public string ClassName = "Falcon";
        [TextArea] public string Lore;

        [Header("Base Stats")]
        public float MaxHealth = 150f;
        public float Armor = 10f;
        public float FlightSpeed = 12f;
        public float Acceleration = 20f;
        public float TurnSpeed = 6f;
        public float DamageMultiplier = 1f;

        [Header("Utility")] 
        public float CarryCapacity = 1f;
        public float EggCarrySpeedPenalty = 0.75f;
    }
}
