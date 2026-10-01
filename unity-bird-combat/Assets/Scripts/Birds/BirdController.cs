using UnityEngine;
using BirdCombat.Match;
using BirdCombat.Interactables;

namespace BirdCombat.Birds
{
    [RequireComponent(typeof(Rigidbody))]
    [DisallowMultipleComponent]
    public class BirdController : MonoBehaviour
    {
        [SerializeField] private BirdClassDefinition classDefinition;
        [SerializeField] private BirdAbility[] abilities;
        [SerializeField] private float stamina = 100f;
        [SerializeField] private float staminaRegenPerSecond = 15f;
        [SerializeField] private float knockbackResistance = 0.2f;

        public bool IsAlive => currentHealth > 0f;
        public float CurrentHealth => currentHealth;
        public float CurrentStamina => currentStamina;
        public TeamState OwningTeam { get; private set; }
        public MatchManager MatchManager { get; private set; }

        private Rigidbody body;
        private float currentHealth;
        private float currentStamina;
        private EggCarrier eggCarrier;

        private void Awake()
        {
            body = GetComponent<Rigidbody>();
            eggCarrier = GetComponent<EggCarrier>();
            ResetStats();

            if (abilities == null)
                return;

            foreach (var ability in abilities)
            {
                ability?.Initialize(this);
            }
        }

        private void Update()
        {
            if (!IsAlive)
                return;

            currentStamina = Mathf.Min(stamina, currentStamina + staminaRegenPerSecond * Time.deltaTime);
        }

        public void Initialize(TeamState team, MatchManager matchManager)
        {
            OwningTeam = team;
            MatchManager = matchManager;
            if (team != null && !team.ActiveBirds.Contains(this))
            {
                team.ActiveBirds.Add(this);
            }
        }

        public void ResetStats()
        {
            currentHealth = classDefinition != null ? classDefinition.MaxHealth : 150f;
            currentStamina = stamina;
        }

        public bool TryUseAbility(int slot)
        {
            if (abilities == null || slot < 0 || slot >= abilities.Length)
                return false;

            return abilities[slot] != null && abilities[slot].TryExecute();
        }

        public bool HasStamina(float amount) => currentStamina >= amount;

        public bool TryConsumeStamina(float amount)
        {
            if (!HasStamina(amount))
                return false;

            currentStamina -= amount;
            return true;
        }

        public void ApplyDamage(float rawDamage, BirdController instigator)
        {
            if (!IsAlive)
                return;

            float mitigated = rawDamage;
            if (classDefinition != null && classDefinition.Armor > 0)
            {
                mitigated = Mathf.Max(1f, rawDamage - classDefinition.Armor);
            }

            currentHealth -= mitigated;
            if (currentHealth <= 0f)
            {
                currentHealth = 0f;
                Die(instigator);
            }
        }

        public void AddImpulse(Vector3 impulse)
        {
            if (body == null)
                return;

            body.AddForce(impulse * (1f - knockbackResistance), ForceMode.VelocityChange);
        }

        private void Die(BirdController instigator)
        {
            eggCarrier?.DropEgg(true);
            body.velocity = Vector3.zero;
            MatchManager?.ReportBirdDown(this, instigator);
        }

        public void Respawn(Transform spawnPoint)
        {
            ResetStats();
            if (spawnPoint != null)
            {
                transform.SetPositionAndRotation(spawnPoint.position, spawnPoint.rotation);
                body.velocity = Vector3.zero;
            }
        }

        public void PickUpEgg(NestController originNest)
        {
            eggCarrier?.AttachEgg(originNest);
        }

        public void DeliverEgg(NestController friendlyNest)
        {
            eggCarrier?.CaptureEgg(friendlyNest);
        }
    }
}
