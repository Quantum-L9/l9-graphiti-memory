import { randomUUID } from 'node:crypto';
import {
  TaskComplexity,
  type BudgetConfig,
  type BudgetReservation,
  type BudgetState,
  type TaskDescriptor,
} from '../types.js';

export const DEFAULT_BUDGET_CONFIG: BudgetConfig = Object.freeze({
  monthlyBudgetPerClient: 200,
  weeklyTarget: 50,
  weeklyHardCeiling: 100,
  globalMonthlyHardCeiling: 2_000,
  surgeThreshold: 0.6,
});

export enum ThrottleLevel { NONE = 'none', SOFT = 'soft', HARD = 'hard' }

export interface ThrottleDecision {
  level: ThrottleLevel;
  reason: string;
  allowTask: boolean;
  forceDowngrade: boolean;
  maxModelTier: 'fast' | 'strategic' | 'critical';
}

export interface GlobalBudgetState {
  monthSpend: number;
  reservedSpend: number;
  ceiling: number;
  utilization: number;
}

export interface BudgetAdmissionInput {
  state: BudgetState;
  config: BudgetConfig;
  task: TaskDescriptor;
  estimatedCost: number;
  globalMonthSpend: number;
  globalReservedSpend: number;
  globalMonthlyHardCeiling: number;
}

export interface BudgetStore {
  initClient(clientId: string, overrides?: Partial<BudgetConfig>): Promise<void>;
  reserveTask(
    clientId: string,
    task: TaskDescriptor,
    estimatedCost: number,
    now?: Date,
    idFactory?: () => string,
  ): Promise<{ decision: ThrottleDecision; reservation: BudgetReservation }>;
  reconcile(reservationId: string, actualCost: number): Promise<void>;
  release(reservationId: string): Promise<void>;
  recordSpend(clientId: string, amount: number): Promise<void>;
  resetDaily(clientId: string): Promise<void>;
  resetWeekly(clientId: string): Promise<void>;
  resetMonthly(clientId: string): Promise<void>;
  resetGlobalMonthly(): Promise<void>;
  checkSurgeAllowance(clientId: string, dayOfWeek: number): Promise<boolean>;
  getClientBudgetReport(clientId: string): Promise<BudgetState>;
  getAllBudgetReports(): Promise<BudgetState[]>;
  getGlobalSpend(): Promise<GlobalBudgetState>;
}

interface ClientRecord {
  state: BudgetState;
  config: BudgetConfig;
}

export function validateBudgetConfig(config: BudgetConfig): void {
  const positiveFields: Array<keyof Omit<BudgetConfig, 'surgeThreshold'>> = [
    'monthlyBudgetPerClient',
    'weeklyTarget',
    'weeklyHardCeiling',
    'globalMonthlyHardCeiling',
  ];
  for (const field of positiveFields) {
    if (!Number.isFinite(config[field]) || config[field] <= 0) throw new RangeError(`${field} must be a finite positive number`);
  }
  if (!Number.isFinite(config.surgeThreshold) || config.surgeThreshold < 0 || config.surgeThreshold > 1) {
    throw new RangeError('surgeThreshold must be between 0 and 1');
  }
  if (config.weeklyTarget > config.weeklyHardCeiling) {
    throw new RangeError('weeklyTarget must not exceed weeklyHardCeiling');
  }
}

export function evaluateBudgetAdmission(input: BudgetAdmissionInput): ThrottleDecision {
  const { state, config, task, estimatedCost, globalMonthSpend, globalReservedSpend, globalMonthlyHardCeiling } = input;
  const projectedMonth = state.monthSpend + state.reservedSpend + estimatedCost;
  const projectedWeek = state.weekSpend + state.reservedSpend + estimatedCost;
  const projectedGlobal = globalMonthSpend + globalReservedSpend + estimatedCost;
  let level = ThrottleLevel.NONE;
  if (projectedMonth > state.monthlyBudget
      || projectedGlobal > globalMonthlyHardCeiling
      || (projectedWeek > state.weeklyHardCeiling && !state.surgeAllowance)) {
    level = ThrottleLevel.HARD;
  } else if (projectedWeek > state.weekTarget || projectedMonth > state.monthlyBudget * 0.8) {
    level = ThrottleLevel.SOFT;
  }

  // Hard ceilings are invariant. Model downgrade cannot make an already-priced
  // reservation safe because the reservation amount was calculated before this
  // decision. Reject and let the caller retry with a newly priced task.
  if (level === ThrottleLevel.HARD) {
    return { level, reason: 'Hard budget ceiling reached; task deferred', allowTask: false, forceDowngrade: false, maxModelTier: 'fast' };
  }
  // Critical tasks may bypass soft throttling, but never a hard ceiling.
  if (task.complexity === TaskComplexity.CRITICAL) {
    return { level: ThrottleLevel.NONE, reason: 'Critical task admitted within hard ceilings', allowTask: true, forceDowngrade: false, maxModelTier: 'critical' };
  }
  if (level === ThrottleLevel.SOFT) {
    return { level, reason: 'Soft throttle; cheaper tier required', allowTask: true, forceDowngrade: true, maxModelTier: task.complexity === TaskComplexity.HIGH ? 'strategic' : 'fast' };
  }
  return { level, reason: 'Within budget', allowTask: true, forceDowngrade: false, maxModelTier: 'critical' };
}

export class BudgetTracker {
  private readonly config: BudgetConfig;
  private readonly clients = new Map<string, ClientRecord>();
  private readonly reservations = new Map<string, BudgetReservation>();
  private globalMonthSpend = 0;
  private globalReservedSpend = 0;

  constructor(config: Partial<BudgetConfig> = {}) {
    this.config = { ...DEFAULT_BUDGET_CONFIG, ...config };
    validateBudgetConfig(this.config);
  }

  initClient(clientId: string, overrides?: Partial<BudgetConfig>): void {
    if (clientId.trim().length === 0) throw new RangeError('clientId must not be empty');
    const clientConfig = { ...this.config, ...overrides };
    validateBudgetConfig(clientConfig);
    const existing = this.clients.get(clientId);
    this.clients.set(clientId, {
      config: clientConfig,
      state: existing?.state ?? {
        clientId,
        monthlyBudget: clientConfig.monthlyBudgetPerClient,
        monthSpend: 0,
        weekSpend: 0,
        weekTarget: clientConfig.weeklyTarget,
        todaySpend: 0,
        weeklyHardCeiling: clientConfig.weeklyHardCeiling,
        surgeAllowance: false,
        remainingMonthly: clientConfig.monthlyBudgetPerClient,
        remainingWeekly: clientConfig.weeklyHardCeiling,
        throttleLevel: 'none',
        reservedSpend: 0,
        activeReservations: 0,
      },
    });
    const record = this.getRecord(clientId);
    record.state.monthlyBudget = clientConfig.monthlyBudgetPerClient;
    record.state.weekTarget = clientConfig.weeklyTarget;
    record.state.weeklyHardCeiling = clientConfig.weeklyHardCeiling;
    this.refreshDerived(record);
  }

  evaluateTask(clientId: string, task: TaskDescriptor, estimatedCost: number): ThrottleDecision {
    const record = this.getRecord(clientId);
    return evaluateBudgetAdmission({
      state: record.state,
      config: record.config,
      task,
      estimatedCost,
      globalMonthSpend: this.globalMonthSpend,
      globalReservedSpend: this.globalReservedSpend,
      globalMonthlyHardCeiling: this.config.globalMonthlyHardCeiling,
    });
  }

  reserveTask(
    clientId: string,
    task: TaskDescriptor,
    estimatedCost: number,
    now: Date = new Date(),
    idFactory: () => string = randomUUID,
  ): { decision: ThrottleDecision; reservation: BudgetReservation } {
    if (!Number.isFinite(estimatedCost) || estimatedCost < 0) throw new RangeError('estimatedCost must be a finite non-negative number');
    const decision = this.evaluateTask(clientId, task, estimatedCost);
    if (!decision.allowTask) throw new BudgetReservationError(decision.reason);
    const record = this.getRecord(clientId);
    const reservation: BudgetReservation = { id: idFactory(), clientId, estimatedCost, createdAt: now.toISOString() };
    if (reservation.id.length === 0) throw new BudgetReservationError('Budget reservation ID must not be empty');
    if (this.reservations.has(reservation.id)) throw new BudgetReservationError(`Duplicate budget reservation ID: ${reservation.id}`);
    this.reservations.set(reservation.id, reservation);
    record.state.reservedSpend += estimatedCost;
    record.state.activeReservations += 1;
    this.globalReservedSpend += estimatedCost;
    this.refreshDerived(record);
    return { decision, reservation };
  }

  reconcile(reservationId: string, actualCost: number): void {
    if (!Number.isFinite(actualCost) || actualCost < 0) throw new RangeError('actualCost must be a finite non-negative number');
    const reservation = this.takeReservation(reservationId);
    const record = this.getRecord(reservation.clientId);
    this.releaseReservationAmounts(record, reservation);
    this.commitSpend(record, actualCost);
  }

  release(reservationId: string): void {
    const reservation = this.takeReservation(reservationId);
    const record = this.getRecord(reservation.clientId);
    this.releaseReservationAmounts(record, reservation);
    this.refreshDerived(record);
  }

  recordSpend(clientId: string, amount: number): void {
    if (!Number.isFinite(amount) || amount < 0) throw new RangeError('amount must be a finite non-negative number');
    this.commitSpend(this.getRecord(clientId), amount);
  }

  resetDaily(clientId: string): void { this.getRecord(clientId).state.todaySpend = 0; }
  resetWeekly(clientId: string): void {
    const record = this.getRecord(clientId);
    record.state.weekSpend = 0;
    record.state.surgeAllowance = false;
    this.refreshDerived(record);
  }
  resetMonthly(clientId: string): void {
    const record = this.getRecord(clientId);
    record.state.monthSpend = 0;
    record.state.weekSpend = 0;
    record.state.todaySpend = 0;
    record.state.surgeAllowance = false;
    this.refreshDerived(record);
  }
  resetGlobalMonthly(): void { this.globalMonthSpend = 0; }

  checkSurgeAllowance(clientId: string, dayOfWeek: number): boolean {
    const record = this.getRecord(clientId);
    if (dayOfWeek >= 4 && record.state.weekSpend / record.state.weekTarget < record.config.surgeThreshold) record.state.surgeAllowance = true;
    return record.state.surgeAllowance;
  }

  getClientBudgetReport(clientId: string): BudgetState { return { ...this.getRecord(clientId).state }; }
  getAllBudgetReports(): BudgetState[] { return Array.from(this.clients.values(), entry => ({ ...entry.state })); }
  getGlobalSpend(): GlobalBudgetState {
    return {
      monthSpend: this.globalMonthSpend,
      reservedSpend: this.globalReservedSpend,
      ceiling: this.config.globalMonthlyHardCeiling,
      utilization: (this.globalMonthSpend + this.globalReservedSpend) / this.config.globalMonthlyHardCeiling,
    };
  }

  private getRecord(clientId: string): ClientRecord {
    const record = this.clients.get(clientId);
    if (!record) throw new Error(`Client ${clientId} not initialized. Call initClient() first.`);
    return record;
  }

  private takeReservation(id: string): BudgetReservation {
    const reservation = this.reservations.get(id);
    if (!reservation) throw new Error(`Unknown or already-settled budget reservation: ${id}`);
    this.reservations.delete(id);
    return reservation;
  }

  private releaseReservationAmounts(record: ClientRecord, reservation: BudgetReservation): void {
    record.state.reservedSpend = Math.max(0, record.state.reservedSpend - reservation.estimatedCost);
    record.state.activeReservations = Math.max(0, record.state.activeReservations - 1);
    this.globalReservedSpend = Math.max(0, this.globalReservedSpend - reservation.estimatedCost);
  }

  private commitSpend(record: ClientRecord, amount: number): void {
    record.state.monthSpend += amount;
    record.state.weekSpend += amount;
    record.state.todaySpend += amount;
    this.globalMonthSpend += amount;
    this.refreshDerived(record);
  }

  private refreshDerived(record: ClientRecord): void {
    const state = record.state;
    state.remainingMonthly = state.monthlyBudget - state.monthSpend - state.reservedSpend;
    state.remainingWeekly = state.weeklyHardCeiling - state.weekSpend - state.reservedSpend;
    const decision = evaluateBudgetAdmission({
      state,
      config: record.config,
      task: { type: 'classification' as TaskDescriptor['type'], complexity: TaskComplexity.LOW },
      estimatedCost: 0,
      globalMonthSpend: this.globalMonthSpend,
      globalReservedSpend: this.globalReservedSpend,
      globalMonthlyHardCeiling: this.config.globalMonthlyHardCeiling,
    });
    state.throttleLevel = decision.level;
  }
}

export class InMemoryBudgetStore implements BudgetStore {
  constructor(readonly tracker: BudgetTracker) {}
  async initClient(clientId: string, overrides?: Partial<BudgetConfig>): Promise<void> { this.tracker.initClient(clientId, overrides); }
  async reserveTask(clientId: string, task: TaskDescriptor, estimatedCost: number, now?: Date, idFactory?: () => string) { return this.tracker.reserveTask(clientId, task, estimatedCost, now, idFactory); }
  async reconcile(reservationId: string, actualCost: number): Promise<void> { this.tracker.reconcile(reservationId, actualCost); }
  async release(reservationId: string): Promise<void> { this.tracker.release(reservationId); }
  async recordSpend(clientId: string, amount: number): Promise<void> { this.tracker.recordSpend(clientId, amount); }
  async resetDaily(clientId: string): Promise<void> { this.tracker.resetDaily(clientId); }
  async resetWeekly(clientId: string): Promise<void> { this.tracker.resetWeekly(clientId); }
  async resetMonthly(clientId: string): Promise<void> { this.tracker.resetMonthly(clientId); }
  async resetGlobalMonthly(): Promise<void> { this.tracker.resetGlobalMonthly(); }
  async checkSurgeAllowance(clientId: string, dayOfWeek: number): Promise<boolean> { return this.tracker.checkSurgeAllowance(clientId, dayOfWeek); }
  async getClientBudgetReport(clientId: string): Promise<BudgetState> { return this.tracker.getClientBudgetReport(clientId); }
  async getAllBudgetReports(): Promise<BudgetState[]> { return this.tracker.getAllBudgetReports(); }
  async getGlobalSpend(): Promise<GlobalBudgetState> { return this.tracker.getGlobalSpend(); }
}

export class BudgetReservationError extends Error {
  constructor(message: string) { super(message); this.name = 'BudgetReservationError'; }
}
