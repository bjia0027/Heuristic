#pragma once
#include <functional>
#include <vector>

class Service34 {
public:
    Service34();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
