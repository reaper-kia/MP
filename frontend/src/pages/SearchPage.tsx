import { Stack, Text, Title } from "@mantine/core";
import { useParams } from "react-router";

// Форма поиска — FE-03, ход поиска и подборка — FE-04…FE-07.
export function SearchPage() {
  const { searchId } = useParams();

  return (
    <Stack>
      <Title order={2}>Поиск</Title>
      <Text c="dimmed">Форма поиска появится в FE-03.</Text>
      {searchId && <Text c="dimmed">Подборка по поиску {searchId} появится в FE-04…FE-07.</Text>}
    </Stack>
  );
}
