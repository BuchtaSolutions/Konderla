import { useState } from "react";
import axios from "axios";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardBody, CardHeader } from "@heroui/card";
import { Button } from "@heroui/button";
import { Input } from "@heroui/input";
import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, useDisclosure } from "@heroui/modal";
import { Link } from "@heroui/link";
import DefaultLayout from "@/layouts/default";
import { getProjects, createProject, deleteProject } from "@/lib/api";
import { DeleteIcon } from "@/components/icons";

export default function IndexPage() {
  const { isOpen, onOpen, onOpenChange } = useDisclosure();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onOpenChange: onDeleteOpenChange } = useDisclosure();
  const [newProjectName, setNewProjectName] = useState("");
  const [newProjectDesc, setNewProjectDesc] = useState("");
  const [projectToDelete, setProjectToDelete] = useState<any>(null);
  
  const queryClient = useQueryClient();

  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects
  });

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: async (data: any) => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      
      onOpenChange(); // Close modal
      setNewProjectName("");
      setNewProjectDesc("");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProject(id),
    onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: ['projects'] });
        onDeleteOpenChange();
        setProjectToDelete(null);
    }
  });

  const handleCreate = () => {
    createMutation.mutate({ name: newProjectName, description: newProjectDesc });
  };
  
  const confirmDelete = (project: any) => {
      setProjectToDelete(project);
      onDeleteOpen();
  };

  return (
    <DefaultLayout>
      <section className="flex flex-col items-center justify-center gap-4 py-8 md:py-10">
        <div className="inline-block max-w-lg text-center justify-center">
          <h1 className="text-4xl font-bold">Procurement Projects</h1>
        </div>

        <div className="w-full max-w-4xl px-4">
          <div className="flex justify-end mb-4">
            <Button color="primary" onPress={onOpen}>
              New Project
            </Button>
          </div>

          {isLoading ? (
            <div>Loading...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {projects?.map((project: any) => (
                <Card key={project.id} className="hover:scale-[1.02] transition-transform">
                  <CardHeader className="flex gap-3 justify-between items-start">
                    <div className="flex flex-col">
                      <p className="text-md font-bold">{project.name}</p>
                    </div>
                    <Button isIconOnly size="sm" variant="light" color="danger" onPress={() => confirmDelete(project)}>
                        <DeleteIcon />
                    </Button>
                  </CardHeader>
                  <CardBody>
                    <p>{project.description}</p>
                    <Link href={`/projects/${project.id}`} className="mt-4 text-primary">
                      View Details
                    </Link>
                  </CardBody>
                </Card>
              ))}
            </div>
          )}
        </div>

        <Modal isOpen={isOpen} onOpenChange={onOpenChange}>
          <ModalContent>
            {(onClose) => (
              <>
                <ModalHeader className="flex flex-col gap-1">Create New Project</ModalHeader>
                <ModalBody>
                  <Input 
                    label="Project Name" 
                    value={newProjectName} 
                    onValueChange={setNewProjectName}
                  />
                  <Input 
                    label="Description" 
                    value={newProjectDesc} 
                    onValueChange={setNewProjectDesc}
                  />
                </ModalBody>
                <ModalFooter>
                  <Button color="danger" variant="light" onPress={onClose}>
                    Close
                  </Button>
                  <Button color="primary" onPress={handleCreate} isLoading={createMutation.isPending}>
                    Create
                  </Button>
                </ModalFooter>
              </>
            )}
          </ModalContent>
        </Modal>

        <Modal isOpen={isDeleteOpen} onOpenChange={onDeleteOpenChange}>
          <ModalContent>
            {(onClose) => (
              <>
                <ModalHeader>Delete Project</ModalHeader>
                <ModalBody>
                  <p>Are you sure you want to delete <span className="font-bold">{projectToDelete?.name}</span>?</p>
                  <p className="text-danger">This will delete all rounds, budgets, and files associated with this project. This action cannot be undone.</p>
                </ModalBody>
                <ModalFooter>
                  <Button color="default" variant="light" onPress={onClose}>
                    Cancel
                  </Button>
                  <Button 
                    color="danger" 
                    onPress={() => projectToDelete && deleteMutation.mutate(projectToDelete.id)}
                    isLoading={deleteMutation.isPending}
                  >
                    Delete Project
                  </Button>
                </ModalFooter>
              </>
            )}
          </ModalContent>
        </Modal>
      </section>
    </DefaultLayout>
  );
}
