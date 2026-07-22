import {
  AudioWaveform,
  BrainCircuit,
  Bot,
  Command,
  FileBarChart,
  GalleryVerticalEnd,
  KeyRound,
  LayoutDashboard,
  Network,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  SquareTerminal,
  TestTube2,
  Users,
  Waypoints,
} from 'lucide-react'
import { type SidebarData } from '../types'

export const sidebarData: SidebarData = {
  user: {
    name: 'AIOps Admin',
    email: 'admin@aiops.example.com',
    avatar: '/avatars/shadcn.jpg',
  },
  teams: [
    {
      name: 'AIOps Platform',
      logo: Command,
      plan: 'Enterprise Ops',
    },
    {
      name: 'Core Apps',
      logo: GalleryVerticalEnd,
      plan: 'Production',
    },
    {
      name: 'Plant Ops',
      logo: AudioWaveform,
      plan: 'UAT + MES',
    },
  ],
  navGroups: [
    {
      title: 'Operate',
      items: [
        {
          title: 'Dashboard',
          url: '/',
          icon: LayoutDashboard,
        },
        {
          title: 'Inventory',
          url: '/inventory',
          icon: Server,
        },
        {
          title: 'AI Chat',
          url: '/chats',
          badge: 'live',
          icon: Bot,
        },
        {
          title: 'AI Memory',
          url: '/memory',
          icon: BrainCircuit,
        },
        {
          title: 'Knowledge',
          url: '/knowledge',
          icon: Network,
        },
        {
          title: 'Gateway Terminal',
          url: '/terminal',
          icon: SquareTerminal,
        },
        {
          title: 'Infrastructure Discovery',
          url: '/discovery',
          icon: Waypoints,
        },
      ],
    },
    {
      title: 'Govern',
      items: [
        {
          title: 'Policy',
          url: '/policy',
          icon: ShieldCheck,
        },
        {
          title: 'Audit',
          url: '/audit',
          icon: ScrollText,
        },
        {
          title: 'Reports',
          url: '/reports',
          icon: FileBarChart,
        },
        {
          title: 'Users & RBAC',
          url: '/users',
          icon: Users,
        },
      ],
    },
    {
      title: 'Platform',
      items: [
        {
          title: 'Settings',
          icon: Settings,
          items: [
            {
              title: 'AI Providers',
              url: '/settings',
              icon: Bot,
            },
            {
              title: 'SSH Gateways',
              url: '/settings/account',
              icon: KeyRound,
            },
          ],
        },
        ...(import.meta.env.DEV ? [{
          title: 'Development Test',
          url: '/development-test',
          icon: TestTube2,
        }] : []),
      ],
    },
  ],
}
