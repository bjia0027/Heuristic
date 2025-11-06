#pragma once
#include <functional>
#include <vector>

class Service27 {
public:
    Service27();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
