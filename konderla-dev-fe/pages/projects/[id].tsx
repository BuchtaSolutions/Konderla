import { useRouter } from "next/router";
import React, { useState, useMemo, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Tabs, Tab } from "@heroui/tabs";
import { Table, TableHeader, TableColumn, TableBody, TableRow, TableCell } from "@heroui/table";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Select, SelectItem } from "@heroui/select";
import { Switch } from "@heroui/switch";
import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, useDisclosure } from "@heroui/modal";
import {
  Drawer,
  DrawerContent,
  DrawerHeader,
  DrawerBody,
  DrawerFooter,
} from "@heroui/drawer";
import { Checkbox } from "@heroui/checkbox";
import { Popover, PopoverTrigger, PopoverContent } from "@heroui/popover";
import DefaultLayout from "@/layouts/default";
import { getProject, getRounds, getBudgets, promoteRound, createRound, createBudget, deleteBudget, deleteRound, mergeRoundItems, updateBudget, getBudgetNotes, createBudgetNote, updateProject, deleteProject, detectDuplicates, deleteDuplicate, uploadToDrive, uploadBudgetExcel, exportRoundPdf } from "@/lib/api";
import { Link } from "@heroui/link";
import ChatWidget from "@/components/ChatWidget";
import { DeleteIcon, EditIcon } from "@/components/icons";
import { Textarea } from "@heroui/input";
import { Chip } from "@heroui/chip";
import * as XLSX from "xlsx";

export default function ProjectDetail() {
  const router = useRouter();
  const { id } = router.query;
  const projectId = id as string;
  const queryClient = useQueryClient();
  const [isPresentationMode, setIsPresentationMode] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false); // Default closed
  
  // Round Creation State
  const { isOpen: isRoundOpen, onOpen: onRoundOpen, onOpenChange: onRoundOpenChange } = useDisclosure();
  const [newRoundName, setNewRoundName] = useState("");

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => getProject(projectId),
    enabled: !!projectId
  });

  const { data: rounds } = useQuery({
    queryKey: ['rounds', projectId],
    queryFn: () => getRounds(projectId),
    enabled: !!projectId
  });

  const [selectedRoundId, setSelectedRoundId] = useState<string | null>(null);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  // Update selected round when rounds load
  useMemo(() => {
    if (rounds && rounds.length > 0 && !selectedRoundId) {
      setSelectedRoundId(rounds[0].id);
    }
  }, [rounds]);

  const selectedRound = rounds?.find((r: any) => r.id === selectedRoundId);

  // Project Edit State
  const { isOpen: isEditProjectOpen, onOpen: onEditProjectOpen, onOpenChange: onEditProjectOpenChange } = useDisclosure();
  const [editProjectName, setEditProjectName] = useState("");
  const [editProjectDesc, setEditProjectDesc] = useState("");

  // Lifted state for RoundView
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set([]));
  
  // Clear selection and search when round changes
  useEffect(() => {
    setSelectedKeys(new Set([]));
    setSearchQuery("");
  }, [selectedRoundId]);

  // Round Actions State (Lifted)
  const { isOpen: isPromoteOpen, onOpen: onPromoteOpen, onOpenChange: onPromoteOpenChange } = useDisclosure();
  const [promoteRoundName, setPromoteRoundName] = useState("");
  
  const { isOpen: isBudgetOpen, onOpen: onBudgetOpen, onOpenChange: onBudgetOpenChange } = useDisclosure();
  const [newBudgetName, setNewBudgetName] = useState("");
  const [newBudgetFile, setNewBudgetFile] = useState<File | null>(null);

  const { isOpen: isDeleteRoundOpen, onOpen: onDeleteRoundOpen, onOpenChange: onDeleteRoundOpenChange } = useDisclosure();
  
  const { isOpen: isDeleteProjectOpen, onOpen: onDeleteProjectOpen, onOpenChange: onDeleteProjectOpenChange } = useDisclosure();

  useEffect(() => {
    if (project) {
        setEditProjectName(project.name);
        setEditProjectDesc(project.description || "");
    }
  }, [project, isEditProjectOpen]);

  const updateProjectMutation = useMutation({
    mutationFn: (data: { name: string; description: string }) => updateProject(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      onEditProjectOpenChange();
    }
  });

  const deleteProjectMutation = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
        router.push("/");
    }
  });

  const handleUpdateProject = () => {
    updateProjectMutation.mutate({
        name: editProjectName,
        description: editProjectDesc
    });
  }

  const handleDeleteProject = () => {
      deleteProjectMutation.mutate(projectId);
  }

  const createRoundMutation = useMutation({
    mutationFn: createRound,
    onSuccess: (newRound) => {
      queryClient.invalidateQueries({ queryKey: ['rounds', projectId] });
      onRoundOpenChange();
      setNewRoundName("");
      if (newRound?.id) {
        setSelectedRoundId(newRound.id);
      }
    }
  });

  const deleteRoundMutation = useMutation({
    mutationFn: deleteRound,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rounds', projectId] });
      onDeleteRoundOpenChange();
      // Select first round if available? Effect will handle getting rounds 
    }
  });

  const promoteMutation = useMutation({
    mutationFn: promoteRound,
    onSuccess: (newRound) => {
      queryClient.invalidateQueries({ queryKey: ['rounds', projectId] });
      onPromoteOpenChange();
      setPromoteRoundName("");
      setSelectedKeys(new Set([]));
      if (newRound?.id) {
        setSelectedRoundId(newRound.id);
      }
    }
  });

  const createBudgetMutation = useMutation({
    mutationFn: (variables: { data: FormData, url?: string }) => createBudget(variables.data, variables.url),
    onSuccess: () => {
        if (selectedRoundId) {
            queryClient.invalidateQueries({ queryKey: ['budgets', selectedRoundId] });
        }
        onBudgetOpenChange();
        setNewBudgetName("");
        setNewBudgetFile(null);
    }
  });

  const handleCreateRound = () => {
    const order = rounds ? rounds.length + 1 : 1;
    createRoundMutation.mutate({
      project_id: projectId,
      name: newRoundName,
      order: order
    });
  };

  const handleDeleteRound = () => {
      if (selectedRoundId) {
          deleteRoundMutation.mutate(selectedRoundId);
      }
  };

  const handlePromote = () => {
    if (!selectedRoundId) return;
    const budgetIds = Array.from(selectedKeys);
    promoteMutation.mutate({
      project_id: projectId,
      current_round_id: selectedRoundId,
      budget_ids: budgetIds,
      new_round_name: promoteRoundName
    });
  };

  const handleCreateBudget = async () => {
    if (!selectedRoundId) return;
    
    // Check if it's an Excel file for the new processor
    if (newBudgetFile) {
        const fileName = newBudgetFile.name.toLowerCase();
        if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
             // Use new Excel processor endpoint
             const formData = new FormData();
             formData.append('project_id', projectId);
             formData.append('round_id', selectedRoundId);
             formData.append('file', newBudgetFile);
             if (newBudgetName?.trim()) {
                 formData.append('name', newBudgetName.trim());
             }
             try {
                await uploadBudgetExcel(formData);
                queryClient.invalidateQueries({ queryKey: ['budgets', selectedRoundId] });
                onBudgetOpenChange();
                setNewBudgetName("");
                setNewBudgetFile(null);
                alert("Rozpočet úspěšně nahrán a zpracován.");
                return;
             } catch (e) {
                 console.error("New Excel upload failed, falling back or showing error", e);
                 alert("Chyba při nahrávání Excelu: " + e);
                 // Don't fall back, let the user know provided format is wrong or server error
                 return;
             }
        }
    }

    let customUrl = undefined;
    let csvContent = "";

    if (newBudgetFile) {
      const fileName = newBudgetFile.name.toLowerCase();
      if (fileName.endsWith('.xlsx') || fileName.endsWith('.xls')) {
        customUrl = process.env.NEXT_PUBLIC_N8N_WEBHOOK_EXCEL;
        try {
          const arrayBuffer = await newBudgetFile.arrayBuffer();
          const workbook = XLSX.read(arrayBuffer);
          
          let worksheet = null;
          const priorityNames = ["Stavba", "Krycí list", "Rekapitulace"];
          
          for (const name of priorityNames) {
              if (workbook.Sheets[name]) {
                  worksheet = workbook.Sheets[name];
                  break;
              }
          }

          if (!worksheet && workbook.SheetNames.length > 0) {
             console.warn("Preferred sheets not found, using first sheet:", workbook.SheetNames[0]);
             worksheet = workbook.Sheets[workbook.SheetNames[0]];
          }

          if (worksheet) {
               csvContent = XLSX.utils.sheet_to_csv(worksheet, { blankrows: false });
          }
          
        } catch (e) {
          console.error("Error parsing xlsx", e);
        }
      } else if (fileName.endsWith('.pdf')) {
        customUrl = process.env.NEXT_PUBLIC_N8N_WEBHOOK_PDF;
      }
    }

    const formData = new FormData();
    
    if (customUrl) {
      if (csvContent) {
          formData.append('csvContent', csvContent);
      }
      
      formData.append('name', newBudgetName);
      formData.append('project_id', projectId.toString());
      formData.append('round_id', selectedRoundId.toString());
      
      // If we extracted CSV, we generally don't need to send the file to n8n if it only processes csvContent.
      // But if standard is to send file as backup or for PDF, logic can be:
      if (newBudgetFile && !csvContent) {
        formData.append('file', newBudgetFile);
      }
    } else {
      formData.append('round_id', selectedRoundId.toString());
      formData.append('project_id', projectId.toString());
      formData.append('name', newBudgetName);
      
      // Standard backend always expects 'file'
      if (newBudgetFile) {
        formData.append('file', newBudgetFile);
      }
    }

    createBudgetMutation.mutate({ data: formData, url: customUrl });
  };


  return (
    <DefaultLayout>
      <div className="w-full px-6 py-2">
        {/* Breadcrumbs */}
        <div className="flex items-center gap-2 text-sm text-default-500 mb-2">
          <Link href="/" color="foreground" className="text-sm opacity-60 hover:opacity-100">
            Projekty
          </Link>
          <span>/</span>
          <span className="opacity-60">Kola</span>
          {selectedRound && (
            <>
              <span>/</span>
              <span className="font-medium text-foreground">{selectedRound.name}</span>
            </>
          )}
        </div>

        <div className="flex justify-between items-center mb-2">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold">{project?.name}</h1>
                <Button isIconOnly size="sm" variant="light" onPress={onEditProjectOpen}>
                    <EditIcon className="text-default-400" />
                </Button>
                <Button isIconOnly size="sm" variant="light" color="danger" onPress={onDeleteProjectOpen}>
                    <DeleteIcon className="text-danger-400" />
                </Button>
            </div>
            {project?.description && <p className="text-small text-gray-500">{project?.description}</p>}
          </div>
          <div className="flex items-center gap-2">
            {!isPresentationMode && projectId && (
                <Button 
                    color={isChatOpen ? "primary" : "default"} 
                    variant={isChatOpen ? "solid" : "flat"} 
                    onPress={() => setIsChatOpen(!isChatOpen)}
                    startContent={<span>💬</span>}
                >
                    Chat
                </Button>
            )}
            <Switch isSelected={isPresentationMode} onValueChange={setIsPresentationMode}>
              Prezentační režim
            </Switch>
          </div>
        </div>

        <div className="flex h-[calc(100vh-140px)]">
          <div className="flex-1 flex flex-col min-w-0 overflow-y-auto pr-4">
            {rounds && rounds.length > 0 ? (
              <div className="flex w-full flex-col gap-4">
            <div className="flex flex-wrap items-center justify-between border-b border-divider pb-2 gap-4">
                <div className="flex-none overflow-x-auto max-w-[40%]">
                    <Tabs 
                        aria-label="Rounds" 
                        selectedKey={selectedRoundId?.toString()}
                        onSelectionChange={(key) => setSelectedRoundId(String(key))}
                        variant="underlined"
                        classNames={{
                            tabList: "gap-6 w-full relative rounded-none p-0 border-b-0",
                            cursor: "w-full bg-primary",
                            tab: "max-w-fit px-0 h-10",
                            tabContent: "group-data-[selected=true]:text-primary"
                        }}
                    >
                        {rounds.map((round: any) => (
                            <Tab key={round.id} title={round.name} />
                        ))}
                    </Tabs>
                </div>

                <div className="flex-1 flex justify-center px-4">
                    <Input
                        placeholder="Hledat položky..."
                        value={searchQuery}
                        onValueChange={setSearchQuery}
                        className="w-full max-w-xs"
                        size="sm"
                        startContent={<div className="text-default-400 text-tiny">🔍</div>}
                        isClearable
                    />
                </div>
                
                <div className="flex items-center gap-2 flex-none">
                    {!isPresentationMode && (
                        <>
                            <Button 
                                size="sm"
                                color="danger" 
                                variant="ghost" 
                                onPress={onDeleteRoundOpen}
                            >
                                Smazat kolo
                            </Button>
                            <Button size="sm" color="primary" variant="flat" onPress={onBudgetOpen}>
                                Přidat rozpočet
                            </Button>
                            <Button 
                                size="sm"
                                color="secondary" 
                                isDisabled={selectedKeys.size === 0}
                                onPress={onPromoteOpen}
                            >
                                Postoupit
                            </Button>
                            {selectedRoundId && (
                                <Button 
                                    size="sm"
                                    color="success" 
                                    variant="flat"
                                    isLoading={isExportingPdf}
                                    isDisabled={isExportingPdf}
                                    onPress={async () => {
                                        setIsExportingPdf(true);
                                        try {
                                            await exportRoundPdf(selectedRoundId);
                                        } catch (error) {
                                            console.error("Export failed:", error);
                                            alert("Export PDF selhal. Zkontroluj konzoli pro detaily.");
                                        } finally {
                                            setIsExportingPdf(false);
                                        }
                                    }}
                                >
                                    {isExportingPdf ? "Exportuji..." : "Exportovat PDF"}
                                </Button>
                            )}
                        </>
                    )}
                </div>
            </div>

            {selectedRoundId && (
                <RoundView 
                    key={selectedRoundId}
                    roundId={selectedRoundId} 
                    projectId={projectId} 
                    isPresentationMode={isPresentationMode} 
                    onRoundCreated={(id) => setSelectedRoundId(id)}
                    searchQuery={searchQuery}
                    selectedKeys={selectedKeys}
                    onSelectionChange={setSelectedKeys}
                />
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-xl text-gray-500 mb-4">Pro tento projekt nebyla nalezena žádná kola.</p>
            <Button color="primary" onPress={onRoundOpen}>
              Vytvořit první kolo
            </Button>
          </div>
        )}

        {/* Create Round Modal */}
        <Modal isOpen={isRoundOpen} onOpenChange={onRoundOpenChange}>
          <ModalContent>
            {(onClose) => (
              <>
                <ModalHeader>Vytvořit nové kolo</ModalHeader>
                <ModalBody>
                  <Input 
                    label="Název kola" 
                    placeholder="např. Úvodní nabídka"
                    value={newRoundName}
                    onValueChange={setNewRoundName}
                  />
                </ModalBody>
                <ModalFooter>
                  <Button color="danger" variant="light" onPress={onClose}>
                    Zrušit
                  </Button>
                  <Button color="primary" onPress={handleCreateRound} isLoading={createRoundMutation.isPending}>
                    Vytvořit
                  </Button>
                </ModalFooter>
              </>
            )}
          </ModalContent>
        </Modal>

        {/* Edit Project Modal */}
        <Modal isOpen={isEditProjectOpen} onOpenChange={onEditProjectOpenChange}>
            <ModalContent>
                {(onClose) => (
                    <>
                        <ModalHeader>Upravit projekt</ModalHeader>
                        <ModalBody>
                            <Input
                                label="Název projektu"
                                value={editProjectName}
                                onValueChange={setEditProjectName}
                            />
                            <Textarea
                                label="Popis"
                                value={editProjectDesc}
                                onValueChange={setEditProjectDesc}
                            />
                        </ModalBody>
                        <ModalFooter>
                            <Button variant="light" onPress={onClose}>Zrušit</Button>
                            <Button color="primary" onPress={handleUpdateProject} isLoading={updateProjectMutation.isPending}>Uložit</Button>
                        </ModalFooter>
                    </>
                )}
            </ModalContent>
        </Modal>

        {/* Delete Round Confirmation Modal */}
        <Modal isOpen={isDeleteRoundOpen} onOpenChange={onDeleteRoundOpenChange}>
            <ModalContent>
            {(onClose) => (
                <>
                <ModalHeader>Smazat kolo</ModalHeader>
                <ModalBody>
                    <p>Opravdu chcete smazat toto kolo? Všechny rozpočty v něm budou smazány.</p>
                    <p className="text-sm text-danger font-bold">Tuto akci nelze vzít zpět.</p>
                </ModalBody>
                <ModalFooter>
                    <Button variant="light" onPress={onClose}>
                    Zrušit
                    </Button>
                    <Button color="danger" onPress={handleDeleteRound} isLoading={deleteRoundMutation.isPending}>
                    Smazat
                    </Button>
                </ModalFooter>
                </>
            )}
            </ModalContent>
        </Modal>

      {/* Promote Modal */}
      <Modal isOpen={isPromoteOpen} onOpenChange={onPromoteOpenChange}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Přenést vybrané do nového kola</ModalHeader>
              <ModalBody>
                <p>Vybrané rozpočty ({selectedKeys.size}) budou zkopírovány do nového kola.</p>
                <Input 
                  label="Název nového kola" 
                  placeholder="např. 2. kolo"
                  value={promoteRoundName}
                  onValueChange={setPromoteRoundName}
                />
              </ModalBody>
              <ModalFooter>
                <Button color="danger" variant="light" onPress={onClose}>
                  Zrušit
                </Button>
                <Button color="primary" onPress={handlePromote} isLoading={promoteMutation.isPending}>
                  Postoupit
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

      {/* Create Budget Modal */}
      <Modal isOpen={isBudgetOpen} onOpenChange={onBudgetOpenChange}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Přidat nový rozpočet</ModalHeader>
              <ModalBody>
                <Input 
                  label="Název rozpočtu" 
                  placeholder="např. Dodavatel A"
                  value={newBudgetName}
                  onValueChange={setNewBudgetName}
                />
                <div className="flex flex-col gap-2">
                  <label htmlFor="budget-file-input" className="text-sm font-medium">Soubor rozpočtu (XLSX/PDF)</label>
                  <input 
                    id="budget-file-input"
                    type="file" 
                    onChange={(e) => setNewBudgetFile(e.target.files ? e.target.files[0] : null)}
                    className="block w-full text-sm text-gray-500 mt-2
                        file:mr-4 file:py-2 file:px-4
                        file:rounded-full file:border-0
                        file:text-sm file:font-semibold
                        file:bg-primary-50 file:text-primary-700
                        hover:file:bg-primary-100"
                  />
                </div>
              </ModalBody>
              <ModalFooter>
                <Button color="danger" variant="light" onPress={onClose}>
                  Zrušit
                </Button>
                <Button color="primary" onPress={handleCreateBudget} isLoading={createBudgetMutation.isPending}>
                  Přidat rozpočet
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>
      
          </div> 
          
          {projectId && !isPresentationMode && isChatOpen && (
             <div className="w-[400px] flex-none border-l border-divider bg-default-50 h-full overflow-hidden">
                <ChatWidget projectId={projectId} className="h-full" compact={true} />
             </div>
          )}

        </div>
      </div>

      {/* Delete Project Confirmation Modal */}
      <Modal isOpen={isDeleteProjectOpen} onOpenChange={onDeleteProjectOpenChange}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Smazat projekt</ModalHeader>
              <ModalBody>
                <p>Opravdu chcete smazat <span className="font-bold">{project?.name}</span>?</p>
                <p className="text-danger">Tímto smažete všechna kola, rozpočty a soubory spojené s tímto projektem. Tuto akci nelze vzít zpět.</p>
              </ModalBody>
              <ModalFooter>
                <Button color="default" variant="light" onPress={onClose}>
                  Zrušit
                </Button>
                <Button 
                  color="danger" 
                  onPress={handleDeleteProject}
                  isLoading={deleteProjectMutation.isPending}
                >
                  Smazat projekt
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

    </DefaultLayout>
  );
}

function RoundView({ 
    roundId, 
    projectId, 
    isPresentationMode,
    onRoundCreated,
    searchQuery,
    selectedKeys,
    onSelectionChange
}: { 
    roundId: string, 
    projectId: string, 
    isPresentationMode: boolean,
    onRoundCreated?: (id: string) => void,
    searchQuery: string,
    selectedKeys: Set<string>,
    onSelectionChange: (keys: Set<string>) => void
}) {
  const queryClient = useQueryClient();

  const { data: allBudgets, isLoading } = useQuery({
    queryKey: ['budgets', roundId],
    queryFn: () => getBudgets(roundId)
  });

  // Debug: Log budgets received from API
  useEffect(() => {
    if (allBudgets) {
      console.log('[FE] Received budgets:', allBudgets.length);
      const rootBudgets = allBudgets.filter((b: any) => !b.parent_budget_id);
      const childBudgets = allBudgets.filter((b: any) => b.parent_budget_id);
      console.log('[FE]   - Root budgets:', rootBudgets.length, rootBudgets.map((b: any) => ({ id: b.id, name: b.name })));
      console.log('[FE]   - Child budgets:', childBudgets.length, childBudgets.map((b: any) => ({ id: b.id, name: b.name, parent_budget_id: b.parent_budget_id })));
      
      // Debug: Log items in each root budget
      rootBudgets.forEach((b: any) => {
        const items = getBudgetItems(b);
        console.log(`[FE]   Root budget '${b.name}': ${items.length} items`);
        items.forEach((item: any, idx: number) => {
          console.log(`[FE]     Item ${idx + 1}: number='${item.number || ''}' name='${item.name}' price=${item.price}`);
        });
      });
    }
  }, [allBudgets]);

  // --- Drill Down State ---
  // Stack of "Drill Contexts". Each context defines which budget ID to show for each column.
  // Level 0: Main Parents.
  // Level 1: Selected Item -> Map<ParentID, ChildID>
  const [drillStack, setDrillStack] = useState<Array<{ name: string, budgetMap: Record<string, string> }>>([]);

  const rootBudgets = useMemo(() => {
      // Return only top-level budgets (no parent_budget_id)
      return (allBudgets || []).filter((b: any) => !b.parent_budget_id);
  }, [allBudgets]);

  // Get all child budgets grouped by parent
  const childBudgetsByParent = useMemo(() => {
      const map: Record<string, any[]> = {};
      (allBudgets || []).forEach((b: any) => {
          if (b.parent_budget_id) {
              if (!map[b.parent_budget_id]) {
                  map[b.parent_budget_id] = [];
              }
              map[b.parent_budget_id].push(b);
          }
      });
      return map;
  }, [allBudgets]);

  // The budgets currently being displayed in the columns
  const activeBudgets = useMemo(() => {
     if (drillStack.length === 0) {
         return rootBudgets; // Default: Show only Parents as columns
     }
     
     // Current Drill Level
     const currentLevel = drillStack[drillStack.length - 1];
     const map = currentLevel.budgetMap;
     
     // Return list of budgets based on the map (preserve order of rootBudgets for consistent columns)
     return rootBudgets.map((parent: any) => {
         const childId = map[parent.id];
         // Find actual budget object
         const child = allBudgets?.find((b: any) => b.id === childId);
         // If child exists, return it. If not, return a placeholder or null? 
         // If we return null, the column is empty.
         return child || { id: `empty-${parent.id}`, name: "N/A", items: [], isPlaceholder: true, parent_id: parent.id }; 
     });
  }, [drillStack, rootBudgets, allBudgets]);

  const handleDrillDown = (itemName: string, itemNumber?: string) => {
      // Find children for each active budget matching this item
      const nextMap: Record<string, string> = {};
      let foundAny = false;

      activeBudgets.forEach((b: any) => {
           if (b.isPlaceholder) return;
           
           // We need to look for a Child Budget that links to 'b' (as parent) 
           // AND matches the 'itemName' or 'itemNumber'.
           
           // Strategy 1: Look at the current budget's "items".
           // The clicked row comes from "itemName".
           // Does the item row data contain a link?
           // The backend parsed structure: 
           // Parent Item: { number: "IO 01", name: "Foundation", price: ... }
           // Child Budget: labels: { code: "IO 01" ... }
           
           // So we assume 'itemNumber' (code) is passed if available.
           
           const candidates = allBudgets.filter((child: any) => child.parent_budget_id === b.id);
           
           // Try match by Code first
           let match = candidates.find((child: any) => 
               child.labels?.code && itemNumber && child.labels.code == itemNumber
           );
           
           // Fallback: Match by Name (or if Code inside name)
           if (!match) {
               match = candidates.find((child: any) => 
                  child.name.includes(itemName) || (child.labels?.code && itemName.includes(child.labels.code))
               );
           }
           
           if (match) {
               nextMap[b.is_child ? b.parent_budget_id : b.id] = match.id; // Store link to Root Parent? No, we need consistent columns.
               // Actually, if we are already deep, 'b' is a child.
               // But our columns are defined by 'rootBudgets' in the UI usually.
               // activeBudgets logic above iterates 'rootBudgets' (the columns).
               // So we need to map RootParentID -> NewChildID.
               
               // But wait, 'b' in this loop IS from 'activeBudgets'.
               // If we are at Level 0, 'b' is Root.
               // If we are at Level 1, 'b' is Child. Does Child have Children? (Grandchildren).
               // The logic supports arbitrary depth if 'b' becomes the parent for next level.
               
               // Re-reading logic: 
               // activeBudgets IS computed from rootBudgets structure.
               // So 'b' corresponds to a column for a specific Root Parent.
               // We need to find the *next* child relative to *current* 'b'.
               
               // Correct Logic:
               // match = allBudgets.find(candidate.parent_budget_id == b.id ...)
               
               nextMap[b.parent_budget_id || b.id] = match.id; // This assumes we track back to root or simple parent?
               
               // Actually, activeBudgets logic:
               // `rootBudgets.map(parent => ...)`
               // We need the map to be Keyed by RootParentID.
               // If 'b' is Root (Level 0), b.id is key.
               // If 'b' is Child (Level 1), b.parent_budget_id is key (assuming 1 level).
               
               // If complex hierarchy (Grandchildren), we need to track "Current ID" -> "Next ID".
               // But to keep columns stable, we usually key by the COLUMN ID (Root).
               
               // Let's rely on `rootBudgets` index or ID.
               // `activeBudgets` is aligned with `rootBudgets`.
               
               // We need to know which Root Parent this 'b' belongs to.
               // We can add a property to 'activeBudgets' items or just iterate rootBudgets again?
               
               foundAny = true;
           }
      });
      
      // We need to construct the map properly: RootID -> NextChildID
      const newLevelMap: Record<string, string> = {};
      
      rootBudgets.forEach((root: any, index: number) => {
           // Get currently displayed budget for this root
           const currentBudget = activeBudgets[index];
           if (currentBudget.isPlaceholder) return;
           
           // Find child of 'currentBudget': by code, by parent_item_code (type3 sub-budgets), or by name
           const match = allBudgets.find((child: any) => 
               child.parent_budget_id === currentBudget.id && 
               (
                   (itemNumber && child.labels?.code === itemNumber) ||
                   (itemNumber && child.labels?.parent_item_code === itemNumber) ||
                   (child.name.includes(itemName))
               )
           );
           
           if (match) {
               newLevelMap[root.id] = match.id;
               foundAny = true;
           }
      });

   
  // Helper to extract item number (e.g. from "IO 710 Name" -> "IO 710")
  const getItemNumber = (itemName: string, budget: any) => {
      // Try to find exact item object to get metadata if we stored it
      const items = getBudgetItems(budget);
      const item = items.find((i: any) => i.name === itemName);
      return item?.number || null;
  };
  
  // Can we drill down?
  const canDrillDown = (itemName: string) => {
      // Check if any active budget has a child that matches this item
      return activeBudgets.some((b: any) => {
          if (b.isPlaceholder) return false;
          // Find item code
          const code = getItemNumber(itemName, b);
          // Check children
          return (allBudgets || []).some((child: any) => 
             child.parent_budget_id === b.id && 
             ((code && (child.labels?.code === code || child.labels?.parent_item_code === code)) || child.name.includes(itemName))
          );
      });
  };
      if (foundAny) {
          setDrillStack([...drillStack, { name: itemName, budgetMap: newLevelMap }]);
      }
  };

  const handleDrillUp = () => {
      setDrillStack(prev => prev.slice(0, -1));
  };
  
  // Use activeBudgets for logic below instead of 'budgets'
  // But we need to keep 'budgets' variable name for compatibility or rename all 
  const budgets = activeBudgets; // Alias for the rest of component

  // Debug: Log active budgets
  useEffect(() => {
    if (budgets) {
      console.log('[FE] Active budgets (columns):', budgets.length);
      budgets.forEach((b: any, idx: number) => {
        const getItems = (budget: any) => {
          if (Array.isArray(budget.items)) return budget.items;
          if (budget.items && Array.isArray(budget.items.list)) return budget.items.list;
          return [];
        };
        const items = getItems(b);
        console.log(`[FE]   Column ${idx + 1}: id=${b.id}, name='${b.name}', items=${items.length}, parent_budget_id=${b.parent_budget_id || 'none'}`);
      });
    }
  }, [budgets]);

  // Filter & Sort State
  const [sortOrder, setSortOrder] = useState<string>("default");

  // Delete Budget State
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onOpenChange: onDeleteOpenChange } = useDisclosure();
  const [budgetToDelete, setBudgetToDelete] = useState<string | null>(null);

  // Merge Items State
  const { isOpen: isMergeOpen, onOpen: onMergeOpen, onOpenChange: onMergeOpenChange } = useDisclosure();
  const [mergeSource, setMergeSource] = useState<string | null>(null);
  const [mergeTarget, setMergeTarget] = useState<string | null>(null);
  const [mergeNewName, setMergeNewName] = useState<string>('');
  
  // Duplicates State
  const { isOpen: isDuplicatesOpen, onOpen: onDuplicatesOpen, onOpenChange: onDuplicatesOpenChange } = useDisclosure();
  const [foundDuplicates, setFoundDuplicates] = useState<any[]>([]);

  const detectDuplicatesMutation = useMutation({
    mutationFn: () => detectDuplicates(roundId.toString()),
    onSuccess: (data) => {
        setFoundDuplicates(data);
        if (data && data.length > 0) {
            onDuplicatesOpen();
        } else {
            alert("No duplicates found.");
        }
    },
    onError: (error) => {
        console.error("Failed to detect duplicates:", error);
        alert("Failed to detect duplicates. Check console for details.");
    }
  });

  const deleteDuplicateMutation = useMutation({
      mutationFn: (id: string) => deleteDuplicate(id),
      onSuccess: (deletedDup) => {
          // Remove from local list
          setFoundDuplicates(prev => prev.filter(d => d.id !== deletedDup.id));
      }
  });

  const [isMergingAll, setIsMergingAll] = useState(false);

  const handleMergeAll = async () => {
    if (!confirm("Opravdu chcete sloučit všechny duplicity? Jako výsledný název bude použit první zobrazený.")) return;
    
    setIsMergingAll(true);
    try {
      for (const dup of foundDuplicates) {
          try {
            await mergeRoundItems(roundId.toString(), {
                source_name: dup.data.item_b_name,
                target_name: dup.data.item_a_name,
                new_name: dup.data.item_a_name
            });
            await deleteDuplicate(dup.id);
          } catch (e) {
              console.error(`Failed to merge ${dup.data.item_a_name} and ${dup.data.item_b_name}`, e);
          }
      }
      queryClient.invalidateQueries({ queryKey: ['budgets', roundId] });
      setFoundDuplicates([]);
      onDuplicatesOpenChange();
      alert("Hotovo. Všechny duplicity byly sloučeny.");
    } catch (error) {
        console.error("Batch merge failed", error);
        alert("Při hromadném slučování došlo k chybě.");
    } finally {
        setIsMergingAll(false);
    }
  };


  const mergeItemsMutation = useMutation({
     mutationFn: (data: { roundId: string, req: any }) => mergeRoundItems(data.roundId, data.req),
     onSuccess: () => {
         queryClient.invalidateQueries({ queryKey: ['budgets', roundId] });
         onMergeOpenChange();
         setMergeSource(null);
         setMergeTarget(null);
         setMergeNewName('');
     },
     onError: (error) => {
         console.error("Failed to merge:", error);
         alert("Failed to merge items");
     }
  });

  const handleMerge = () => {
     if (!roundId || !mergeSource || !mergeTarget || !mergeNewName) return;
     mergeItemsMutation.mutate({
         roundId: roundId,
         req: {
             source_name: mergeSource,
             target_name: mergeTarget,
             new_name: mergeNewName
         }
     });
  };

  const handleDragStart = (e: React.DragEvent, itemName: string) => {
      e.dataTransfer.setData("application/item-name", itemName);
      e.dataTransfer.effectAllowed = "move";
  };

  const handleDragOver = (e: React.DragEvent) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (e: React.DragEvent, targetName: string) => {
      e.preventDefault();
      const sourceName = e.dataTransfer.getData("application/item-name");
      if (sourceName && sourceName !== targetName) {
          setMergeSource(sourceName);
          setMergeTarget(targetName);
          setMergeNewName(targetName); 
          onMergeOpen();
      }
  };

  const deleteBudgetMutation = useMutation({
    mutationFn: deleteBudget,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgets', roundId] });
      onDeleteOpenChange();
      setBudgetToDelete(null);
    }
  });

  const { isOpen: isDrawerOpen, onOpen: onDrawerOpen, onOpenChange: onDrawerOpenChange } = useDisclosure();
  const [budgetToEdit, setBudgetToEdit] = useState<any>(null);
  const [editName, setEditName] = useState("");
  const [editScore, setEditScore] = useState<number | null>(null);
  const [editTags, setEditTags] = useState<string[]>([]);
  const [tagInput, setTagInput] = useState("");
  
  // Notes State
  const [newNote, setNewNote] = useState("");
  const { data: budgetNotes, refetch: refetchNotes } = useQuery({
      queryKey: ['budgetNotes', budgetToEdit?.id],
      queryFn: () => getBudgetNotes(budgetToEdit?.id),
      enabled: !!budgetToEdit?.id
  });

  const updateBudgetMutation = useMutation({
    mutationFn: (data: { id: string, updates: any }) => updateBudget(data.id, data.updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['budgets', roundId] });
      // Don't close drawer immediately to allow continued editing
    }
  });
  
  const createNoteMutation = useMutation({
      mutationFn: (data: { id: string, content: string }) => createBudgetNote(data.id, data.content),
      onSuccess: () => {
          setNewNote("");
          refetchNotes();
      }
  });

  const handleUpdateBudget = () => {
      if (!budgetToEdit) return;
      const updates = {
          name: editName,
          score: editScore,
          labels: { tags: editTags } 
      };
      updateBudgetMutation.mutate({ id: budgetToEdit.id, updates });
  };
  
  const handleAddNote = () => {
      if (!budgetToEdit || !newNote.trim()) return;
      createNoteMutation.mutate({ id: budgetToEdit.id, content: newNote });
  };

  const handleItemPriceUpdate = (budget: any, itemName: string, newPrice: number) => {
      const items = [...getBudgetItems(budget)];
      const existingItemIndex = items.findIndex((i: any) => i.name === itemName);

      if (existingItemIndex >= 0) {
          // Update existing
          items[existingItemIndex] = { ...items[existingItemIndex], price: newPrice };
      } else {
          // Add new
          items.push({ name: itemName, price: newPrice });
      }

      updateBudgetMutation.mutate({ 
          id: budget.id, 
          updates: { items: items } 
      });
  };

  const openDrawer = (budget: any) => {
      setBudgetToEdit(budget);
      setEditName(budget.name);
      setEditScore(budget.score);
      setEditTags(Array.isArray(budget.labels?.tags) ? budget.labels.tags : []);
      setTagInput("");
      setNewNote("");
      onDrawerOpen();
  };

  const handleTagKeyDown = (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ',') {
          e.preventDefault();
          const tag = tagInput.trim().replace(',', '');
          if (tag && !editTags.includes(tag)) {
              setEditTags([...editTags, tag]);
              setTagInput("");
          }
      }
  };
  
  const removeTag = (tagToRemove: string) => {
      setEditTags(editTags.filter(t => t !== tagToRemove));
  };

  // Helper to safely get items array
  const getBudgetItems = (budget: any) => {
    if (Array.isArray(budget.items)) return budget.items;
    if (budget.items && Array.isArray(budget.items.list)) return budget.items.list;
    return [];
  };

  // Extract all unique item names from all budgets to build rows
  const allItemNames = useMemo(() => {
    if (!budgets) return [];
    const names = new Set<string>();
    budgets.forEach((budget: any) => {
      const items = getBudgetItems(budget);
      items.forEach((item: any) => {
        if (item.name) names.add(item.name);
      });
    });
    return Array.from(names).sort();
  }, [budgets]);


  // Filter items based on search query
  const filteredItemNames = useMemo(() => {
    if (!searchQuery) return allItemNames;
    return allItemNames.filter(name => 
      name.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [allItemNames, searchQuery]);

  // Sort budgets based on sortOrder
  const sortedBudgets = useMemo(() => {
    if (!budgets) return [];
    const sorted = [...budgets];

    const getBudgetTotal = (b: any) => {
      const items = getBudgetItems(b);
      return items.reduce((sum: number, item: any) => sum + (item.price || 0), 0);
    };

    const getBudgetItemPrice = (b: any, itemName: string) => {
      const items = getBudgetItems(b);
      const item = items.find((i: any) => i.name === itemName);
      return item ? (item.price || 0) : 0;
    };

    if (sortOrder.startsWith('item:')) {
      const lastColonIndex = sortOrder.lastIndexOf(':');
      const direction = sortOrder.substring(lastColonIndex + 1);
      const itemName = sortOrder.substring(5, lastColonIndex);
      
      return sorted.sort((a, b) => {
        const valA = getBudgetItemPrice(a, itemName);
        const valB = getBudgetItemPrice(b, itemName);
        return direction === 'asc' ? valA - valB : valB - valA;
      });
    }

    switch (sortOrder) {
      case "price-asc":
        return sorted.sort((a, b) => getBudgetTotal(a) - getBudgetTotal(b));
      case "price-desc":
        return sorted.sort((a, b) => getBudgetTotal(b) - getBudgetTotal(a));
      case "score-desc":
        return sorted.sort((a, b) => (b.score || 0) - (a.score || 0));
      case "name-asc":
        return sorted.sort((a, b) => a.name.localeCompare(b.name));
      case "name-desc":
        return sorted.sort((a, b) => b.name.localeCompare(a.name));
      default:
        return sorted;
    }
  }, [budgets, sortOrder]);

  const toggleSort = (key: string) => {
    if (key === 'price') {
      setSortOrder(current => current === 'price-asc' ? 'price-desc' : 'price-asc');
    } else if (key === 'score') {
      setSortOrder(current => current === 'score-desc' ? 'default' : 'score-desc'); // Toggle score sort
    } else if (key === 'name') {
      setSortOrder(current => current === 'name-asc' ? 'name-desc' : 'name-asc');
    } else {
      // It's an item name
      setSortOrder(current => {
         if (current === `item:${key}:asc`) {
             return `item:${key}:desc`;
         }
         return `item:${key}:asc`;
      });
    }
  };

  // Helper to extract item number (e.g. from "IO 710 Name" -> "IO 710")
  const getItemNumber = (itemName: string, budget: any) => {
      // Try to find exact item object to get metadata if we stored it
      const items = getBudgetItems(budget);
      const item = items.find((i: any) => i.name === itemName);
      return item?.number || null;
  };
  
  // Can we drill down?
  const canDrillDown = (itemName: string) => {
      // Check if any active budget has a child that matches this item
      return activeBudgets.some((b: any) => {
          if (b.isPlaceholder) return false;
          // Find item code
          const code = getItemNumber(itemName, b);
          // Check children
          return (allBudgets || []).some((child: any) => 
             child.parent_budget_id === b.id && 
             ((code && (child.labels?.code === code || child.labels?.parent_item_code === code)) || child.name.includes(itemName))
          );
      });
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Zpět na parent – vždy nahoře, když jste v detailu (drill-down) */}
      {drillStack.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap bg-primary-50 dark:bg-primary-500/10 border border-primary-200 dark:border-primary-500/30 p-3 rounded-lg sticky top-0 z-20 shadow-sm">
          <Button
            size="sm"
            color="primary"
            variant="solid"
            onPress={() => setDrillStack([])}
            startContent={<span aria-hidden>←</span>}
          >
            Zpět na hlavní rozpočet
          </Button>
          <span className="text-default-500 text-sm">/</span>
          {drillStack.map((level, i) => (
            <React.Fragment key={i}>
              <Button
                size="sm"
                variant={i === drillStack.length - 1 ? "flat" : "light"}
                color="primary"
                onPress={() => setDrillStack((prev) => prev.slice(0, i + 1))}
              >
                {level.name}
              </Button>
              {i < drillStack.length - 1 && <span className="text-default-400">/</span>}
            </React.Fragment>
          ))}
          <Button size="sm" variant="light" color="default" onPress={handleDrillUp} className="ml-auto">
            O úroveň zpět
          </Button>
        </div>
      )}

      <Table 
        aria-label="Rozpočty projektu"
        classNames={{
            base: "max-h-[calc(100vh-300px)] overflow-scroll",
            table: "min-h-[400px]",
        }}
        isHeaderSticky
      >
        <TableHeader>
          <TableColumn key="item" className="min-w-[200px] z-10 bg-background/90 backdrop-blur-md">
            <Button 
                variant="light" 
                className="p-0 min-w-0 h-auto font-bold flex items-center gap-2"
                onPress={() => toggleSort('name')}
            >
                Položka
                {sortOrder.startsWith('name') && (
                  <span className="text-xs font-normal">{sortOrder === 'name-asc' ? '↑' : '↓'}</span>
                )}
            </Button>
          </TableColumn>
          {(sortedBudgets || []).map((budget: any) => {
            // Pokud je to child budget (má parent_budget_id), zobrazit název parent budgetu
            const displayName = budget.parent_budget_id && drillStack.length > 0 
              ? rootBudgets.find((p: any) => {
                  const currentLevel = drillStack[drillStack.length - 1];
                  return currentLevel.budgetMap[p.id] === budget.id;
                })?.name || budget.name
              : budget.name;
            
            return (
            <TableColumn key={budget.id} className="min-w-[150px]">
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                    <span className="font-bold text-large truncate max-w-[120px]" title={displayName}>{displayName}</span>
                    {budget.isPlaceholder && (
                        <span className="text-tiny px-1 rounded bg-default-200 text-default-600">N/A</span>
                    )}
                    {budget.parent_budget_id && drillStack.length > 0 && (
                        <span className="text-tiny px-1 rounded bg-primary-100 text-primary-700" title={budget.name}>
                          {budget.name}
                        </span>
                    )}
                </div>
                {!budget.isPlaceholder && !isPresentationMode && (
                  <div className="flex gap-1 opacity-100 transition-opacity">
                    <Button
                      isIconOnly
                      color="primary"
                      variant="light"
                      size="sm"
                      onPress={() => openDrawer(budget)}
                    >
                      <EditIcon />
                    </Button>
                    <Button
                      isIconOnly
                      color="danger"
                      variant="light"
                      size="sm"
                      onPress={() => {
                        setBudgetToDelete(budget.id);
                        onDeleteOpen();
                      }}
                    >
                      <DeleteIcon />
                    </Button>
                  </div>
                )}
              </div>
            </TableColumn>
          );
          })}
        </TableHeader>
        <TableBody>
          {/* 1. Total Price Row */}
          <TableRow key="total-price" className="bg-primary-50">
            <TableCell>
              <Button 
                variant="light"
                className="p-0 min-w-0 h-auto font-bold hover:text-primary data-[hover=true]:bg-transparent flex items-center gap-2"
                onPress={() => toggleSort('price')}
                disableRipple
              >
                CELKOVÁ CENA
                {sortOrder.startsWith('price') && (
                  <span className="text-xs font-normal">
                    {sortOrder === 'price-asc' ? '↑' : '↓'}
                  </span>
                )}
              </Button>
            </TableCell>
            {(sortedBudgets || []).map((budget: any) => {
               if (budget.isPlaceholder) return <TableCell key={budget.id}>-</TableCell>;
               const totalFromLabel = budget.labels?.total_price;
               const total = typeof totalFromLabel === 'number' ? totalFromLabel : getBudgetItems(budget).reduce((sum: number, item: any) => sum + (item.price || 0), 0);
               return <TableCell key={budget.id} className="font-bold text-primary">{total.toLocaleString()} Kč</TableCell>;
            })}
          </TableRow>

          {/* 2. Score Row */}
          <TableRow key="score">
            <TableCell>
               <Button 
                variant="light"
                className="p-0 min-w-0 h-auto text-gray-500 font-medium hover:text-primary data-[hover=true]:bg-transparent flex items-center gap-2"
                onPress={() => toggleSort('score')}
                disableRipple
              >
                Skóre
                {sortOrder.startsWith('score') && (
                  <span className="text-xs font-normal">↓</span>
                )}
              </Button>
            </TableCell>
            {(sortedBudgets || []).map((budget: any) => (
               <TableCell key={budget.id} className="font-bold">{budget.isPlaceholder ? '-' : (budget.score ?? '-')}</TableCell>
            ))}
          </TableRow>

           {/* 3.1 Tags Row */}
           <TableRow key="tags">
            <TableCell className="text-gray-500 font-medium">Štítky</TableCell>
            {(sortedBudgets || []).map((budget: any) => (
               <TableCell key={budget.id}>
                   <div className="flex flex-wrap gap-1">
                       {(!budget.isPlaceholder && budget.labels?.tags || []).map((tag: string, i: number) => (
                           <Chip key={i} size="sm" variant="flat" className="bg-blue-100 text-blue-700">
                               {tag}
                           </Chip>
                       ))}
                   </div>
               </TableCell>
            ))}
          </TableRow>

          {/* 4. Dynamic Item Rows */}
          {filteredItemNames.map((itemName: string) => {
            // Check drift availability
            const isDrillable = canDrillDown(itemName);
            
            // Calculate stats for this item
            const itemPrices: number[] = [];
            (sortedBudgets || []).forEach((b: any) => {
                 if (b.isPlaceholder) return;
                 const items = getBudgetItems(b);
                 const item = items.find((i: any) => i.name === itemName);
                 if (item && typeof item.price === 'number') {
                     itemPrices.push(item.price);
                 }
            });

            const stats = itemPrices.length > 0 ? {
                min: Math.min(...itemPrices),
                max: Math.max(...itemPrices),
                avg: Math.round(
                    itemPrices.filter(p => p !== 0).reduce((a, b) => a + b, 0) / 
                    (itemPrices.filter(p => p !== 0).length || 1)
                )
            } : undefined;

            return (
            <TableRow 
              key={itemName}
              draggable
              onDragStart={(e) => handleDragStart(e, itemName)}
              onDragOver={handleDragOver}
              onDrop={(e) => handleDrop(e, itemName)}
              className="cursor-move group"
            >
              <TableCell>
                 <div className="flex items-center gap-2">
                 {isDrillable ? (
                     <Button 
                       isIconOnly size="sm" variant="light" 
                       onPress={() => {
                           // Try to get code from first available budget
                           const b = activeBudgets.find((b: any) => !b.isPlaceholder);
                           const code = b ? getItemNumber(itemName, b) : undefined;
                           handleDrillDown(itemName, code);
                       }}
                       className="text-primary"
                     >
                        ▶
                     </Button>
                 ) : (
                     <span className="text-gray-300 group-hover:text-gray-500 cursor-grab px-1 w-8 text-center">⋮⋮</span>
                 )}
                 
                 <Button 
                   variant="light"
                   className={`p-0 min-w-0 h-auto font-normal hover:text-primary data-[hover=true]:bg-transparent flex items-center gap-2 justify-start w-full text-left ${
                     sortOrder.startsWith(`item:${itemName}`) ? 'text-primary font-medium' : 'text-default-700'
                   }`}
                   onPress={() => isDrillable ? handleDrillDown(itemName, activeBudgets.find((b:any)=>!b.isPlaceholder)?getItemNumber(itemName, activeBudgets.find((b:any)=>!b.isPlaceholder)):undefined) : toggleSort(itemName)}
                   disableRipple
                 >
                   {itemName}
                   {sortOrder.startsWith(`item:${itemName}`) && (
                     <span className="text-xs">{sortOrder.endsWith('asc') ? '↑' : '↓'}</span>
                   )}
                 </Button>
                 </div>
              </TableCell>
              {(sortedBudgets || []).map((budget: any) => {
                 if (budget.isPlaceholder) {
                     return <TableCell key={budget.id} className="text-default-300 text-xs italic">N/A</TableCell>;
                 }
                 
                 const items = getBudgetItems(budget);
                 const item = items.find((i: any) => i.name === itemName);
                 const price = item ? item.price : null;
                 
                 return <TableCell key={budget.id}>
                   <PriceCell 
                     price={price} 
                     onUpdate={(newPrice) => handleItemPriceUpdate(budget, itemName, newPrice)} 
                     stats={stats}
                   />
                 </TableCell>;
              })}
            </TableRow>
            );
          })}
        </TableBody>
      </Table>

      {/* Budget Drawer */}
      <Drawer isOpen={isDrawerOpen} onOpenChange={onDrawerOpenChange} size="2xl">
        <DrawerContent>
          {(onClose) => (
            <>
              <DrawerHeader className="flex flex-col gap-1">Upravit detail rozpočtu</DrawerHeader>
              <DrawerBody>
                <div className="flex flex-col gap-6">
                    {/* General Info */}
                    <div className="flex flex-col gap-2">
                        <h3 className="text-lg font-semibold">Obecné</h3>
                        <Input 
                        label="Název rozpočtu" 
                        value={editName}
                        onValueChange={setEditName}
                        />
                        <Input 
                        label="Skóre" 
                        type="number"
                        placeholder="0-100"
                        value={editScore?.toString() || ""}
                        onValueChange={(val) => setEditScore(val ? parseFloat(val) : null)}
                        description="Zadejte skóre pro tento rozpočet"
                        />
                    </div>

                    {/* Tags Section */}
                     <div className="flex flex-col gap-2">
                        <h3 className="text-lg font-semibold">Štítky</h3>
                        <div className="flex flex-wrap gap-2 mb-2 p-2 bg-content2 rounded-medium min-h-[40px]">
                            {editTags.map((tag) => (
                                <Chip key={tag} onClose={() => removeTag(tag)} variant="flat" color="secondary">
                                    {tag}
                                </Chip>
                            ))}
                            {editTags.length === 0 && <span className="text-default-400 text-sm italic">Žádné štítky</span>}
                        </div>
                        <Input
                        label="Přidat štítek"
                        placeholder="Napište a stiskněte Enter nebo čárku..."
                        value={tagInput}
                        onValueChange={setTagInput}
                        onKeyDown={handleTagKeyDown}
                        description="Stiskněte Enter nebo čárku pro přidání štítku"
                        />
                    </div>

                    {/* Notes History Section */}
                    <div className="flex flex-col gap-4 flex-grow">
                        <div className="flex items-center justify-between">
                             <h3 className="text-lg font-semibold">Poznámky</h3>
                             <span className="text-tiny text-default-400">{budgetNotes?.length || 0} poznámek</span>
                        </div>

                        {/* Input Area - Top */}
                        <div className="flex flex-col gap-2">
                            <Textarea
                                placeholder="Napište svou poznámku zde..."
                                value={newNote}
                                onValueChange={setNewNote}
                                minRows={2}
                                variant="bordered"
                                className="w-full"
                            />
                            <div className="flex justify-end">
                                <Button 
                                    size="sm" 
                                    color="primary" 
                                    onPress={handleAddNote} 
                                    isLoading={createNoteMutation.isPending}
                                    isDisabled={!newNote.trim()}
                                >
                                    Přidat poznámku
                                </Button>
                            </div>
                        </div>

                        {/* List Area - Bottom & Clean */}
                        <div className="flex flex-col gap-0 mt-2 max-h-[400px] overflow-y-auto pr-2">
                            {budgetNotes && budgetNotes.length > 0 ? (
                                budgetNotes.map((note: any) => (
                                    <div key={note.id} className="py-4 border-b border-divider last:border-none">
                                        <p className="text-sm text-foreground whitespace-pre-wrap mb-1">{note.content}</p>
                                        <span className="text-tiny text-default-400">
                                            {new Date(note.created_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}
                                        </span>
                                    </div>
                                ))
                            ) : (
                                <div className="py-8 text-center text-default-400 border border-dashed border-divider rounded-medium bg-default-50/50">
                                    Zatím žádné poznámky.
                                </div>
                            )}
                        </div>
                    </div>
                </div>
              </DrawerBody>
              <DrawerFooter>
                <Button color="danger" variant="light" onPress={onClose}>
                  Zavřít
                </Button>
                <Button color="primary" onPress={handleUpdateBudget} isLoading={updateBudgetMutation.isPending}>
                  Uložit změny
                </Button>
              </DrawerFooter>
            </>
          )}
        </DrawerContent>
      </Drawer>

      
      {/* Merge Items Modal */}
      <Modal isOpen={isMergeOpen} onOpenChange={onMergeOpenChange}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Sloučit položky</ModalHeader>
              <ModalBody>
                <p>Chystáte se sloučit <span className="font-bold">{mergeSource}</span> do <span className="font-bold">{mergeTarget}</span>.</p>
                <p className="text-sm text-gray-500">Tímto se sloučí ceny tam, kde je to možné. Pokud existují obě, budou sečteny.</p>
                <Input 
                  label="Nový název položky" 
                  value={mergeNewName}
                  onValueChange={setMergeNewName}
                />
              </ModalBody>
              <ModalFooter>
                 <Button color="danger" variant="light" onPress={onClose}>
                  Zrušit
                </Button>
                <Button color="primary" onPress={handleMerge} isLoading={mergeItemsMutation.isPending}>
                  Sloučit
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

      
      {/* Duplicates Modal */}
      <Modal isOpen={isDuplicatesOpen} onOpenChange={onDuplicatesOpenChange} size="3xl" scrollBehavior="inside">
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Nalezené potenciální duplicity</ModalHeader>
              <ModalBody className="p-6">
                 {foundDuplicates.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-12 text-center text-default-400">
                        <div className="w-16 h-16 bg-default-100 rounded-full flex items-center justify-center mb-4">
                            <span className="text-2xl">✓</span>
                        </div>
                        <p className="text-lg font-medium text-default-600">Žádné duplicity nenalezeny</p>
                        <p className="text-sm">Skvělá práce! Položky rozpočtu vypadají v pořádku.</p>
                    </div>
                 ) : (
                    <div className="flex flex-col gap-4">
                        <div className="flex items-center justify-between px-1 pb-2 border-b border-divider">
                             <div className="text-sm text-default-500">
                                Nalezeno <span className="font-bold text-default-800">{foundDuplicates.length}</span> potenciálních duplicit
                             </div>
                             <div className="text-xs text-default-400">
                                Zkontrolujte a slučte položky pro sjednocení rozpočtu.
                             </div>
                        </div>

                        <div className="flex flex-col gap-3">
                        {foundDuplicates.map((dup) => (
                            <div key={dup.id} className="group relative flex flex-col sm:flex-row gap-4 justify-between items-center p-4 rounded-large border border-divider hover:bg-content2/50 transition-colors bg-content1/50">
                                <div className="flex-1 w-full sm:w-auto min-w-0">
                                     <div className="flex items-center gap-2 mb-3">
                                        <Chip 
                                            size="sm" 
                                            color={dup.data.match_type === 'exact' ? "danger" : "warning"} 
                                            variant="flat" 
                                            classNames={{
                                                base: "h-6",
                                                content: "uppercase text-[10px] font-bold tracking-wider"
                                            }}
                                        >
                                            {dup.data.match_type.replace('_', ' ')}
                                        </Chip>
                                        <span className="text-xs text-default-400 font-medium">
                                            Podobnost: <span className={dup.data.similarity > 0.9 ? "text-success" : "text-warning"}>{Math.round(dup.data.similarity * 100)}%</span>
                                        </span>
                                     </div>
                                     
                                     <div className="flex md:flex-row flex-col gap-3 text-sm w-full items-stretch relative">
                                         <div className="flex-1 flex flex-col gap-2">
                                             <div className="p-2.5 rounded-medium bg-default-100/50 border border-transparent group-hover:border-default-200 transition-colors font-medium text-default-700 text-center break-words" title={dup.data.item_a_name}>
                                                {dup.data.item_a_name}
                                             </div>
                                             <Button 
                                                 size="sm" 
                                                 className="w-full"
                                                 color="primary" 
                                                 variant="flat"
                                                 onPress={() => {
                                                     // Keep A (Target A, Source B)
                                                     setMergeSource(dup.data.item_b_name);
                                                     setMergeTarget(dup.data.item_a_name);
                                                     setMergeNewName(dup.data.item_a_name);
                                                     onMergeOpen();
                                                     deleteDuplicateMutation.mutate(dup.id);
                                                 }}
                                             >
                                                Zachovat
                                             </Button>
                                         </div>

                                         <div className="text-default-300 flex items-center justify-center py-2 md:py-0">
                                            <svg className="w-5 h-5 rotate-90 md:rotate-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" /></svg>
                                         </div>

                                         <div className="flex-1 flex flex-col gap-2">
                                             <div className="p-2.5 rounded-medium bg-default-100/50 border border-transparent group-hover:border-default-200 transition-colors font-medium text-default-700 text-center break-words" title={dup.data.item_b_name}>
                                                {dup.data.item_b_name}
                                             </div>
                                             <Button 
                                                 size="sm" 
                                                 className="w-full"
                                                 color="primary" 
                                                 variant="flat"
                                                 onPress={() => {
                                                     // Keep B (Target B, Source A)
                                                     setMergeSource(dup.data.item_a_name);
                                                     setMergeTarget(dup.data.item_b_name);
                                                     setMergeNewName(dup.data.item_b_name);
                                                     onMergeOpen();
                                                     deleteDuplicateMutation.mutate(dup.id);
                                                 }}
                                             >
                                                Zachovat
                                             </Button>
                                         </div>
                                     </div>
                                </div>

                                <div className="flex sm:flex-col gap-2 w-full sm:w-auto shrink-0 justify-end sm:border-l border-divider sm:pl-4">
                                    <Button 
                                        size="sm" 
                                        variant="flat" 
                                        className="text-default-500 hover:text-danger hover:bg-danger-50"
                                        onPress={() => deleteDuplicateMutation.mutate(dup.id)}
                                    >
                                        Ignorovat
                                    </Button>
                                </div>
                            </div>
                        ))}
                        </div>
                    </div>
                 )}
              </ModalBody>
              <ModalFooter className="border-t border-divider">
                {foundDuplicates.length > 0 && (
                    <Button 
                        color="primary" 
                        variant="shadow"
                        onPress={handleMergeAll} 
                        isLoading={isMergingAll}
                        startContent={!isMergingAll && <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" /></svg>}
                    >
                        Sloučit vše ({foundDuplicates.length})
                    </Button>
                )}
                <Button color="danger" variant="light" onPress={onClose}>
                  Zavřít
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

      {/* Delete Budget Confirmation Modal */}
      <Modal isOpen={isDeleteOpen} onOpenChange={onDeleteOpenChange}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader>Potvrdit smazání</ModalHeader>
              <ModalBody>
                <p>Opravdu chcete smazat tento rozpočet? Tuto akci nelze vzít zpět.</p>
              </ModalBody>
              <ModalFooter>
                <Button color="default" variant="light" onPress={onClose}>
                  Zrušit
                </Button>
                <Button 
                  color="danger" 
                  onPress={() => budgetToDelete && deleteBudgetMutation.mutate(budgetToDelete)} 
                  isLoading={deleteBudgetMutation.isPending}
                >
                  Smazat
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

    </div>
  );
}

function PriceCell({ price, onUpdate, stats }: { price: number | null, onUpdate: (price: number) => void, stats?: { min: number, max: number, avg: number } }) {
    const [isOpen, setIsOpen] = useState(false);
    const [val, setVal] = useState(price !== null ? price.toString() : "");

    // Sync state if price changes externally
    useEffect(() => {
        setVal(price !== null ? price.toString() : "");
    }, [price, isOpen]); // Reset when opening too

    const handleSave = () => {
        const num = parseFloat(val);
        if (!isNaN(num)) {
            onUpdate(num);
            setIsOpen(false);
        }
    };
    
    // Handle Enter key
    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleSave();
        }
    };

    const getStyle = () => {
        if (price === null || !stats) return {};
        
        // Linear interpolation from Green (lowest price) to Red (highest price)
        const range = stats.max - stats.min;
        let ratio = 0;

        if (range > 0) {
             ratio = (price - stats.min) / range;
        }
        
        // HSL: 120 (Green) -> 0 (Red)
        // ratio 0 -> 120, ratio 1 -> 0
        const hue = 120 * (1 - ratio);
        
        return {
            backgroundColor: `hsla(${hue}, 80%, 85%, 0.6)`,
            border: `1px solid hsla(${hue}, 80%, 40%, 0.3)`
        };
    };

    return (
        <Popover isOpen={isOpen} onOpenChange={setIsOpen} placement="top">
            <PopoverTrigger>
                <div 
                  className="cursor-pointer transition-colors px-2 py-1 rounded-md min-w-[60px] text-right font-mono text-sm"
                  style={getStyle()}
                  title="Click to edit price"
                >
                    {price != null ? price.toLocaleString() : '-'}
                </div>
            </PopoverTrigger>
            <PopoverContent>
                <div className="px-1 py-1 w-full flex flex-col gap-2">
                    <div className="flex gap-2 items-center">
                         <Input 
                            autoFocus
                            size="sm" 
                            type="number" 
                            value={val} 
                            onValueChange={setVal} 
                            aria-label="Price"
                            className="w-32"
                            endContent={<span className="text-default-400 text-tiny">Kč</span>}
                            onKeyDown={handleKeyDown}
                         />
                         <Button size="sm" color="primary" onPress={handleSave}>Uložit</Button>
                    </div>
                    {stats && (
                        <div className="flex justify-between gap-1">
                            <Chip 
                                size="sm" 
                                color="success" 
                                variant="flat" 
                                classNames={{ base: "cursor-pointer hover:opacity-80 active:scale-95 transition-transform" }}
                                onClick={() => setVal(stats.min.toString())}
                            >
                                Min: {stats.min}
                            </Chip>
                            <Chip 
                                size="sm" 
                                color="primary" 
                                variant="flat" 
                                classNames={{ base: "cursor-pointer hover:opacity-80 active:scale-95 transition-transform" }}
                                onClick={() => setVal(stats.avg.toString())}
                            >
                                Avg: {stats.avg}
                            </Chip>
                            <Chip 
                                size="sm" 
                                color="warning" 
                                variant="flat" 
                                classNames={{ base: "cursor-pointer hover:opacity-80 active:scale-95 transition-transform" }}
                                onClick={() => setVal(stats.max.toString())}
                            >
                                Max: {stats.max}
                            </Chip>
                        </div>
                    )}
                </div>
            </PopoverContent>
        </Popover>
    )
}
