export interface Settings {
  injuryDate: string; // YYYY-MM-DD
  side: 'right' | 'left';
  nextAppointment: string | null; // YYYY-MM-DD
  nextImaging: string | null; // YYYY-MM-DD
  doctorClinic: string;
  hideNicotineCheck: boolean;
  darkMode: boolean;
}

export interface DailyLog {
  date: string; // YYYY-MM-DD
  castOk: boolean;
  fingersMoving: boolean;
  noWarningSymptoms: boolean;
  proteinNutrition: boolean;
  calciumNutrition: boolean;
  safeActivity: boolean;
  noNicotine: boolean;
  note: string;
}

export interface WeeklyCheckIn {
  weekKey: string; // YYYY-Www (ISO week)
  completedDate: string;
  castComfortable: boolean;
  fingerMovementNormal: boolean;
  noNewSymptoms: boolean;
  noFallOrTrauma: boolean;
  appointmentConfirmed: boolean;
  unusualNote: string;
}

export type MedDocType =
  | 'ct_report'
  | 'ct_images'
  | 'doctor_notes'
  | 'prescriptions'
  | 'appointments'
  | 'other';

export interface MedicalDoc {
  id: string;
  type: MedDocType;
  title: string;
  date: string;
  note: string;
  reference: string;
}

export interface AppData {
  settings: Settings;
  dailyLogs: DailyLog[];
  weeklyCheckIns: WeeklyCheckIn[];
  medicalDocs: MedicalDoc[];
}

export type Tab = 'home' | 'today' | 'timeline' | 'medical';
